"""用户服务。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from radio.db import get_session_factory
from radio.db.models import User
from radio.db.statements import insert_ignore


class UserService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession] | None = None) -> None:
        self._sf = session_factory

    def _factory(self) -> async_sessionmaker[AsyncSession]:
        return self._sf or get_session_factory()

    async def ensure(self, user_id: str) -> None:
        """不存在则创建（并发安全）。"""
        async with self._factory()() as s:
            stmt = insert_ignore(User.__table__, {"user_id": user_id}, index_elements=["user_id"])
            await s.execute(stmt)
            await s.commit()

    async def is_banned(self, user_id: str) -> bool:
        async with self._factory()() as s:
            row = await s.get(User, user_id)
            return bool(row is not None and row.is_banned)

    async def set_banned(self, user_id: str, banned: bool) -> bool:
        """设置封禁状态；封禁不存在的用户时直接以封禁状态创建（预封禁）。"""
        async with self._factory()() as s:
            row = await s.get(User, user_id)
            if row is None:
                if not banned:
                    return False
                s.add(User(user_id=user_id, is_banned=True))
                await s.commit()
                return True
            row.is_banned = bool(banned)
            await s.commit()
            return True

    async def list_banned(self) -> list[str]:
        async with self._factory()() as s:
            rows = (
                await s.execute(select(User.user_id).where(User.is_banned.is_(True)))
            ).scalars().all()
            return list(rows)
