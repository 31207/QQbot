"""点歌服务：点歌流程的唯一业务实现（bot 确定性指令与 LLM 工具共用）。

竞态处理：
- 同一用户的点歌请求用进程内 per-user 锁串行化（额度检查 → 计数写入原子化）；
- ``user_requests`` 的置顶/计数用单条 ``INSERT ... ON CONFLICT DO UPDATE`` 原子完成，
  跨进程（bot / web 双写）也不会重复插入或丢计数。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from radio.db import get_session_factory
from radio.db.models import Song, UserRequest
from radio.db.statements import insert_update
from radio.services.permissions import Permissions
from radio.services.songs import SongService
from radio.services.users import UserService
from radio.util import today_key, week_key


@dataclass
class OrderResult:
    ok: bool
    first: bool = False
    used: int = 0
    limit: int = 0
    period: str = ""
    reason: str = ""  # banned_user / banned_song / quota / none


class RequestService:
    _MAX_LOCKS = 64

    def __init__(
        self,
        songs: SongService,
        users: UserService,
        permissions: Permissions,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self.songs = songs
        self.users = users
        self.permissions = permissions
        self._sf = session_factory
        self._locks: dict[str, asyncio.Lock] = {}

    def _factory(self) -> async_sessionmaker[AsyncSession]:
        return self._sf or get_session_factory()

    # ---------------------------------------------------------------- 锁

    def _lock_for(self, user_id: str) -> asyncio.Lock:
        lock = self._locks.get(user_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[user_id] = lock
        return lock

    def sweep_locks(self) -> None:
        """维护任务调用：锁数量超限时清理空闲锁（进程内用户数有界）。"""
        if len(self._locks) <= self._MAX_LOCKS:
            return
        idle = [uid for uid, lock in self._locks.items() if not lock.locked()]
        for uid in idle[: len(self._locks) - self._MAX_LOCKS]:
            self._locks.pop(uid, None)

    # ---------------------------------------------------------------- 点歌

    async def order(self, user_id: str, song_info: dict) -> OrderResult:
        """点歌主流程：查歌 → 禁播检查 → 额度检查 → 写入（原子置顶+计数）。"""
        async with self._lock_for(user_id):
            song = await self.songs.get_or_create(song_info)
            if song["is_banned"]:
                return OrderResult(ok=False, reason="banned_song")

            period, limit = self.permissions.role_limit(user_id)
            used = await self.count(user_id, period)
            if used >= limit:
                return OrderResult(ok=False, period=period, limit=limit, reason="quota")

            await self.users.ensure(user_id)
            first = await self._bump(user_id, song["id"])
            used = await self.count(user_id, period)
            return OrderResult(
                ok=True, first=first, used=used, limit=limit, period=period
            )

    async def count(self, user_id: str, period: str) -> int:
        """周期内已点次数：今天=当日计数之和，本周=周计数之和。"""
        now = datetime.now()
        if period == "今天":
            key_col, count_col, key = UserRequest.day, UserRequest.day_count, today_key(now)
        else:
            key_col, count_col, key = UserRequest.week, UserRequest.week_count, week_key(now)
        async with self._factory()() as s:
            value = await s.scalar(
                select(func.coalesce(func.sum(count_col), 0)).where(
                    UserRequest.user_id == user_id, key_col == key
                )
            )
            return int(value or 0)

    async def _bump(self, user_id: str, song_id: int) -> bool:
        """置顶点歌记录并累计当日/本周次数（单条原子语句）；返回是否首次点歌。"""
        now = datetime.now()
        values = {
            "user_id": user_id,
            "song_id": song_id,
            "time": now,
            "day": today_key(now),
            "day_count": 1,
            "week": week_key(now),
            "week_count": 1,
        }
        factory = self._factory()
        async with factory() as s:
            exists = (
                await s.scalar(
                    select(UserRequest.id).where(
                        UserRequest.user_id == user_id, UserRequest.song_id == song_id
                    )
                )
            ) is not None
            stmt = insert_update(
                UserRequest.__table__,
                values,
                {
                    "time": values["time"],
                    "day": values["day"],
                    "day_count": case(
                        (UserRequest.day == values["day"], UserRequest.day_count + 1),
                        else_=1,
                    ),
                    "week": values["week"],
                    "week_count": case(
                        (UserRequest.week == values["week"], UserRequest.week_count + 1),
                        else_=1,
                    ),
                },
                constraint="uq_ur_user_song",
            )
            await s.execute(stmt)
            await s.commit()
            return not exists

    # ---------------------------------------------------------------- 备注 / 歌单 / 重置

    async def set_remark(self, user_id: str, song_id: int, remark: str) -> bool:
        async with self._factory()() as s:
            row = (
                await s.execute(
                    select(UserRequest).where(
                        UserRequest.user_id == user_id, UserRequest.song_id == song_id
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                return False
            row.remark = remark or ""
            await s.commit()
            return True

    async def list_for_user(self, user_id: str, limit: int = 20) -> list[dict]:
        async with self._factory()() as s:
            rows = (
                await s.execute(
                    select(
                        UserRequest.time,
                        UserRequest.remark,
                        Song.id.label("song_id"),
                        Song.name,
                        Song.artist,
                        Song.album,
                        Song.cover,
                        Song.source,
                    )
                    .join(Song, Song.id == UserRequest.song_id)
                    .where(UserRequest.user_id == user_id)
                    .order_by(UserRequest.time.desc(), UserRequest.id.desc())
                    .limit(limit)
                )
            ).mappings().all()
            return [dict(r) for r in rows]

    async def reset_all(self) -> int:
        """清零所有人今天/本周的已点次数，返回受影响记录数。"""
        now = datetime.now()
        async with self._factory()() as s:
            res_day = await s.execute(
                update(UserRequest)
                .where(UserRequest.day == today_key(now))
                .values(day_count=0)
            )
            res_week = await s.execute(
                update(UserRequest)
                .where(UserRequest.week == week_key(now))
                .values(week_count=0)
            )
            await s.commit()
            return (res_day.rowcount or 0) + (res_week.rowcount or 0)
