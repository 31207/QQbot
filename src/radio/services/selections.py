"""选用记录服务：查询用户点过的歌里已被广播站选用的歌曲。"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from radio.db import get_session_factory
from radio.db.models import PlayHistory, Song, UserRequest


class SelectionService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession] | None = None) -> None:
        self._sf = session_factory

    def _factory(self) -> async_sessionmaker[AsyncSession]:
        return self._sf or get_session_factory()

    async def list_for_user(self, user_id: str, limit: int = 20) -> list[dict]:
        """用户点过且已被选用的歌曲，按最近选用时间倒序（同一首歌只保留最近一次）。"""
        async with self._factory()() as s:
            rows = (
                await s.execute(
                    select(
                        Song.id.label("song_id"),
                        Song.name,
                        Song.artist,
                        Song.album,
                        Song.cover,
                        Song.source,
                        func.max(PlayHistory.played_at).label("selected_at"),
                    )
                    .join(UserRequest, UserRequest.song_id == Song.id)
                    .join(PlayHistory, PlayHistory.song_id == Song.id)
                    .where(UserRequest.user_id == user_id)
                    .group_by(
                        Song.id,
                        Song.name,
                        Song.artist,
                        Song.album,
                        Song.cover,
                        Song.source,
                    )
                    .order_by(func.max(PlayHistory.played_at).desc())
                    .limit(limit)
                )
            ).mappings().all()
            return [dict(r) for r in rows]
