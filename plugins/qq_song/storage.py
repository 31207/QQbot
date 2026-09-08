"""点歌存储（SQLAlchemy 支持 SQLite / PostgreSQL）：歌曲库、用户、点歌记录。

连接串从环境变量 DATABASE_URL 读取（未设置时用本地 SQLite data/song_requests.db），
与 web 管理后台共用同一 db 层（db.py）。
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select, update

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # 项目根，供 import db

from db import SessionLocal, Song, User, UserRequest, SongSelectedNotice, init_db  # noqa: E402


class SongRequestStore:
    """点歌存储：与 web 共用 model，DATABASE_URL 决定 SQLite/PG。"""

    def __init__(self, path: str | Path | None = None) -> None:
        # 兼容旧版传入 path：若显式给了 sqlite 文件且未设置 DATABASE_URL，则回退到它。
        if path and not os.environ.get("DATABASE_URL"):
            os.environ["DATABASE_URL"] = f"sqlite:///{Path(path).as_posix()}"
        init_db()

    def _session(self):
        return SessionLocal()

    def get_or_create_song(self, info: dict) -> dict:
        """按 (source, source_id) 查找歌曲；不存在则初始化 is_banned=0、play_count=0 后入库。"""
        source = str(info.get("source") or "")
        source_id = str(info.get("id") or "")
        now = datetime.now().isoformat(timespec="seconds")
        with self._session() as s:
            row = s.execute(
                select(Song).where(Song.source == source, Song.source_id == source_id)
            ).scalar_one_or_none()
            if row is None:
                row = Song(
                    source=source,
                    source_id=source_id,
                    name=str(info.get("name") or ""),
                    artist=str(info.get("artist") or ""),
                    album=str(info.get("album") or ""),
                    cover=str(info.get("cover") or ""),
                    duration=int(info.get("duration") or 0),
                    url=str(info.get("url") or ""),
                    link=str(info.get("link") or ""),
                    is_banned=False,
                    play_count=0,
                    created_at=now,
                )
                s.add(row)
                s.commit()
                s.refresh(row)
            return {
                "id": row.id,
                "source": row.source,
                "source_id": row.source_id,
                "name": row.name,
                "artist": row.artist,
                "album": row.album,
                "cover": row.cover,
                "duration": row.duration,
                "url": row.url,
                "link": row.link,
                "is_banned": row.is_banned,
                "play_count": row.play_count,
                "created_at": row.created_at,
                "selected": row.selected,
            }

    def ensure_user(self, user_id: str) -> None:
        with self._session() as s:
            if s.get(User, user_id) is None:
                s.add(
                    User(
                        user_id=user_id,
                        created_at=datetime.now().isoformat(timespec="seconds"),
                    )
                )
                s.commit()

    def get_user(self, user_id: str) -> dict | None:
        with self._session() as s:
            row = s.get(User, user_id)
            if row is None:
                return None
            return {
                "user_id": row.user_id,
                "is_banned": row.is_banned,
                "created_at": row.created_at,
            }

    def is_user_banned(self, user_id: str) -> bool:
        row = self.get_user(user_id)
        return bool(row and row["is_banned"])

    def set_user_banned(self, user_id: str, banned: bool) -> bool:
        """设置用户封禁状态；封禁不存在的用户时直接以封禁状态创建（预封禁）。"""
        with self._session() as s:
            row = s.get(User, user_id)
            if row is None:
                if not banned:
                    return False
                s.add(
                    User(
                        user_id=user_id,
                        is_banned=True,
                        created_at=datetime.now().isoformat(timespec="seconds"),
                    )
                )
                s.commit()
                return True
            row.is_banned = bool(banned)
            s.commit()
            return True

    def list_banned_users(self) -> list[dict]:
        with self._session() as s:
            rows = s.execute(
                select(User).where(User.is_banned.is_(True))
            ).scalars().all()
            return [
                {"user_id": r.user_id, "is_banned": r.is_banned, "created_at": r.created_at}
                for r in rows
            ]

    def add_or_bump_request(self, user_id: str, song_id: int) -> bool:
        """点歌入库：首次点歌插入新记录；重复点歌更新时间为当前（置顶）并累计当日次数。

        返回是否为首次点歌。
        """
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        week = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
        ts = now.isoformat(timespec="seconds")
        with self._session() as s:
            row = s.execute(
                select(UserRequest).where(
                    UserRequest.user_id == user_id,
                    UserRequest.song_id == song_id,
                )
            ).scalar_one_or_none()
            if row is None:
                s.add(
                    UserRequest(
                        user_id=user_id,
                        song_id=song_id,
                        time=ts,
                        day=today,
                        day_count=1,
                        week=week,
                        week_count=1,
                    )
                )
                s.commit()
                return True
            row.time = ts
            row.day = today
            row.day_count = row.day_count + 1 if row.day == today else 1
            row.week = week
            row.week_count = row.week_count + 1 if row.week == week else 1
            s.commit()
            return False

    def set_remark(self, user_id: str, song_id: int, remark: str) -> bool:
        """设置/清除用户对某首歌的备注；返回是否命中该用户的点歌记录。"""
        with self._session() as s:
            row = s.execute(
                select(UserRequest).where(
                    UserRequest.user_id == user_id,
                    UserRequest.song_id == song_id,
                )
            ).scalar_one_or_none()
            if row is None:
                return False
            row.remark = remark or ""
            s.commit()
            return True

    def list_for_user(self, user_id: str, limit: int = 20) -> list[dict]:
        with self._session() as s:
            rows = s.execute(
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
            ).mappings().all()
            return [dict(r) for r in rows]

    def count_for_user_today(self, user_id: str, today: str | None = None) -> int:
        if today is None:
            today = datetime.now().strftime("%Y-%m-%d")
        with self._session() as s:
            value = s.scalar(
                select(func.coalesce(func.sum(UserRequest.day_count), 0)).where(
                    UserRequest.user_id == user_id,
                    UserRequest.day == today,
                )
            )
            return int(value or 0)

    def count_for_user_week(self, user_id: str, week: str | None = None) -> int:
        """统计用户本周已点歌次数（按周计数 week_count 求和）。默认当前自然周（周一起）。"""
        if week is None:
            now = datetime.now()
            week = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
        with self._session() as s:
            value = s.scalar(
                select(func.coalesce(func.sum(UserRequest.week_count), 0)).where(
                    UserRequest.user_id == user_id,
                    UserRequest.week == week,
                )
            )
            return int(value or 0)

    def reset_all_daily_counts(self) -> int:
        """把所有人“今天”的已点次数清零，返回清零的记录数。"""
        today = datetime.now().strftime("%Y-%m-%d")
        with self._session() as s:
            res = s.execute(
                update(UserRequest)
                .where(UserRequest.day == today)
                .values(day_count=0)
            )
            s.commit()
            return res.rowcount or 0

    def reset_all_weekly_counts(self) -> int:
        """把所有人“本周”的已点次数清零，返回清零的记录数。"""
        now = datetime.now()
        week = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
        with self._session() as s:
            res = s.execute(
                update(UserRequest)
                .where(UserRequest.week == week)
                .values(week_count=0)
            )
            s.commit()
            return res.rowcount or 0

    def set_song_banned(self, song_id: int, banned: bool) -> bool:
        """按歌曲库 id 设置禁播状态；返回是否命中。"""
        with self._session() as s:
            row = s.get(Song, song_id)
            if row is None:
                return False
            row.is_banned = bool(banned)
            s.commit()
            return True

    def find_songs_by_name(self, name: str) -> list[dict]:
        """按歌名模糊查找歌曲（最多 20 条）。"""
        with self._session() as s:
            rows = s.execute(
                select(Song).where(Song.name.like(f"%{name}%")).limit(20)
            ).scalars().all()
            return [
                {
                    "id": r.id,
                    "source": r.source,
                    "source_id": r.source_id,
                    "name": r.name,
                    "artist": r.artist,
                    "album": r.album,
                    "cover": r.cover,
                    "duration": r.duration,
                    "url": r.url,
                    "link": r.link,
                    "is_banned": r.is_banned,
                    "play_count": r.play_count,
                    "created_at": r.created_at,
                    "selected": r.selected,
                }
                for r in rows
            ]

    def set_song_banned_by_name(self, name: str, banned: bool) -> int:
        """按歌名模糊设置禁播状态，返回受影响条数。"""
        with self._session() as s:
            res = s.execute(
                update(Song)
                .where(Song.name.like(f"%{name}%"))
                .values(is_banned=bool(banned))
            )
            s.commit()
            return res.rowcount or 0

    # ---------------- 歌曲选中通知缓存 ----------------

    def list_song_requesters(self, song_id: int) -> list[str]:
        """去重返回点过某首歌的所有用户 QQ 号（用于选中后通知）。"""
        with self._session() as s:
            rows = s.execute(
                select(UserRequest.user_id)
                .where(UserRequest.song_id == song_id)
                .distinct()
            ).scalars().all()
            return list(rows)

    def add_selected_notice(
        self,
        song_id: int,
        name: str,
        artist: str,
        user_ids: list[str],
    ) -> None:
        """记录一条「歌曲被选用」的待通知缓存（不立即发送）。"""
        if not user_ids:
            return
        import json as _json

        selected_at = datetime.now().isoformat(timespec="seconds")
        with self._session() as s:
            s.add(
                SongSelectedNotice(
                    song_id=song_id,
                    name=name,
                    artist=artist,
                    selected_at=selected_at,
                    user_ids=_json.dumps(list(dict.fromkeys(user_ids)), ensure_ascii=False),
                    sent=False,
                    sent_at="",
                )
            )
            s.commit()

    def list_pending_notices(self) -> list[dict]:
        """读取所有尚未发送的选中通知缓存记录。"""
        import json as _json

        with self._session() as s:
            rows = s.execute(
                select(SongSelectedNotice)
                .where(SongSelectedNotice.sent.is_(False))
                .order_by(SongSelectedNotice.id.asc())
            ).scalars().all()
            out = []
            for r in rows:
                try:
                    uids = _json.loads(r.user_ids or "[]")
                except Exception:
                    uids = []
                out.append(
                    {
                        "id": r.id,
                        "song_id": r.song_id,
                        "name": r.name,
                        "artist": r.artist,
                        "selected_at": r.selected_at,
                        "user_ids": uids,
                    }
                )
            return out

    def mark_notice_sent(self, notice_id: int) -> None:
        """把某条选中通知标记为已发送。"""
        with self._session() as s:
            row = s.get(SongSelectedNotice, notice_id)
            if row:
                row.sent = True
                row.sent_at = datetime.now().isoformat(timespec="seconds")
                s.commit()
