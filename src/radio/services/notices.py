"""歌曲选用通知缓存：web 写入，bot 定时发送。

只重试上一轮失败的用户；累计尝试达到上限后放弃（标记已发送），
避免每周重复打扰已收到通知的用户。审核被拒的用户单独记录，不再重试。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from radio.db import get_session_factory
from radio.db.models import SongSelectedNotice, UserRequest

logger = logging.getLogger("radio.notices")

MAX_ATTEMPTS = 3


def _load_ids(raw: str) -> list[str]:
    try:
        ids = json.loads(raw or "[]")
        return [str(x) for x in ids] if isinstance(ids, list) else []
    except json.JSONDecodeError:
        return []


class NoticeService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession] | None = None) -> None:
        self._sf = session_factory

    def _factory(self) -> async_sessionmaker[AsyncSession]:
        return self._sf or get_session_factory()

    async def add(self, song_id: int, name: str, artist: str) -> bool:
        """写入一条待通知缓存（含该歌所有点歌用户，去重）；无人点过则跳过。"""
        async with self._factory()() as s:
            uids = list(
                (
                    await s.execute(
                        select(UserRequest.user_id)
                        .where(UserRequest.song_id == song_id)
                        .distinct()
                    )
                ).scalars().all()
            )
        if not uids:
            return False
        async with self._factory()() as s:
            s.add(
                SongSelectedNotice(
                    song_id=song_id,
                    name=name,
                    artist=artist,
                    selected_at=datetime.now(),
                    user_ids=json.dumps(list(dict.fromkeys(uids)), ensure_ascii=False),
                    failed_user_ids="[]",
                    attempts=0,
                    sent=False,
                )
            )
            await s.commit()
            return True

    async def pending(self) -> list[dict]:
        """所有未发送的通知（含上一轮失败用户，用于本轮重试）。"""
        async with self._factory()() as s:
            rows = (
                await s.execute(
                    select(SongSelectedNotice)
                    .where(SongSelectedNotice.sent.is_(False))
                    .order_by(SongSelectedNotice.id.asc())
                )
            ).scalars().all()
        out = []
        for r in rows:
            all_ids = _load_ids(r.user_ids)
            failed = _load_ids(r.failed_user_ids)
            rejected = set(_load_ids(r.rejected_user_ids))
            retry = failed if r.attempts else all_ids
            out.append(
                {
                    "id": r.id,
                    "song_id": r.song_id,
                    "name": r.name,
                    "artist": r.artist,
                    "selected_at": r.selected_at,
                    "user_ids": [uid for uid in retry if uid not in rejected],
                }
            )
        return out

    async def pending_count(self) -> int:
        """未发送通知条数。"""
        async with self._factory()() as s:
            return int(
                await s.scalar(
                    select(func.count())
                    .select_from(SongSelectedNotice)
                    .where(SongSelectedNotice.sent.is_(False))
                )
                or 0
            )

    async def status(self) -> tuple[list[dict], int, list[dict]]:
        """返回 (待发送列表, 已发送数量, 失败列表)。"""
        async with self._factory()() as s:
            rows = (
                await s.execute(
                    select(SongSelectedNotice).order_by(SongSelectedNotice.id.desc())
                )
            ).scalars().all()
        pending: list[dict] = []
        failed: list[dict] = []
        sent_count = 0
        for r in rows:
            failed_ids = list(
                dict.fromkeys([*_load_ids(r.failed_user_ids), *_load_ids(r.rejected_user_ids)])
            )
            item = {
                "id": r.id,
                "name": r.name,
                "artist": r.artist,
                "selected_at": r.selected_at,
                "attempts": r.attempts,
                "failed_user_ids": failed_ids,
            }
            if not r.sent:
                rejected = set(_load_ids(r.rejected_user_ids))
                retry = _load_ids(r.failed_user_ids) if r.attempts else _load_ids(r.user_ids)
                item["user_ids"] = [uid for uid in retry if uid not in rejected]
                pending.append(item)
            elif item["failed_user_ids"]:
                failed.append(item)
            else:
                sent_count += 1
        return pending, sent_count, failed

    async def mark_attempt(
        self,
        notice_id: int,
        failed_user_ids: list[str],
        rejected_user_ids: list[str] = (),
    ) -> None:
        """记录一轮发送结果：全部成功即完成；失败则只留失败用户，达上限后放弃。

        审核被拒的用户单独记录，不再重试，仅在状态中显示为发送失败。
        """
        async with self._factory()() as s:
            row = await s.get(SongSelectedNotice, notice_id)
            if row is None or row.sent:
                return
            row.attempts += 1
            row.failed_user_ids = json.dumps(list(failed_user_ids), ensure_ascii=False)
            rejected = list(
                dict.fromkeys([*_load_ids(row.rejected_user_ids), *rejected_user_ids])
            )
            row.rejected_user_ids = json.dumps(rejected, ensure_ascii=False)
            if not failed_user_ids or row.attempts >= MAX_ATTEMPTS:
                row.sent = True
                row.sent_at = datetime.now()
                if failed_user_ids or rejected:
                    logger.warning(
                        "选中通知 #%s 放弃重试：%s 发送失败",
                        notice_id,
                        [*failed_user_ids, *rejected],
                    )
            await s.commit()
