"""歌曲库服务。"""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from qqbot.db import get_session_factory
from qqbot.db.models import Song
from qqbot.db.statements import insert_ignore

_SONG_COLUMNS = (
    "id", "source", "source_id", "name", "artist", "album", "cover",
    "duration", "url", "link", "is_banned", "play_count", "created_at", "selected",
)


def _row_dict(row: Song) -> dict:
    return {c: getattr(row, c) for c in _SONG_COLUMNS}


class SongService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession] | None = None) -> None:
        self._sf = session_factory

    def _factory(self) -> async_sessionmaker[AsyncSession]:
        return self._sf or get_session_factory()

    async def get_or_create(self, info: dict) -> dict:
        """按 (source, source_id) 查找；不存在则原子插入（并发冲突安全）。"""
        source = str(info.get("source") or "")
        source_id = str(info.get("id") or "")
        values = {
            "source": source,
            "source_id": source_id,
            "name": str(info.get("name") or ""),
            "artist": str(info.get("artist") or ""),
            "album": str(info.get("album") or ""),
            "cover": str(info.get("cover") or ""),
            "duration": int(info.get("duration") or 0),
            "url": str(info.get("url") or ""),
            "link": str(info.get("link") or ""),
            "is_banned": False,
            "play_count": 0,
            "selected": False,
        }
        factory = self._factory()
        async with factory() as s:
            stmt = insert_ignore(
                Song.__table__,
                values,
                constraint="uq_songs_source_srcid",
            )
            await s.execute(stmt)
            await s.commit()
            row = (
                await s.execute(
                    select(Song).where(Song.source == source, Song.source_id == source_id)
                )
            ).scalar_one()
            return _row_dict(row)

    async def set_banned(self, song_id: int, banned: bool) -> bool:
        async with self._factory()() as s:
            row = await s.get(Song, song_id)
            if row is None:
                return False
            row.is_banned = bool(banned)
            await s.commit()
            return True

    async def set_banned_by_name(self, name: str, banned: bool) -> int:
        async with self._factory()() as s:
            res = await s.execute(
                update(Song).where(Song.name.like(f"%{name}%")).values(is_banned=bool(banned))
            )
            await s.commit()
            return res.rowcount or 0
