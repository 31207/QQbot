"""异步数据库层（SQLAlchemy 2.0 async + asyncpg，仅支持 PostgreSQL）。

- 连接串来自 :mod:`qqbot.config` 的 DATABASE_URL（必填）。
- engine / session 工厂惰性创建：首次使用时才解析配置，天然规避导入顺序问题。
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from .models import Base

_engine: AsyncEngine | None = None
_factory: async_sessionmaker[AsyncSession] | None = None


def _pg_url(url: str) -> str:
    """校验并规整 PostgreSQL 连接串（自动补 asyncpg 驱动）。"""
    if not url:
        raise RuntimeError(
            "未配置 DATABASE_URL。请在 .env 中设置，例如：\n"
            "DATABASE_URL=postgresql+asyncpg://user:pass@127.0.0.1:5432/qqbot"
        )
    if not url.startswith("postgresql"):
        raise RuntimeError(f"DATABASE_URL 必须是 PostgreSQL 连接串，当前为：{url}")
    if "+asyncpg" not in url:
        return url.replace("postgresql", "postgresql+asyncpg", 1)
    return url


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        from qqbot.config import settings

        _engine = create_async_engine(_pg_url(settings.database_url), echo=False, pool_pre_ping=True)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _factory
    if _factory is None:
        _factory = async_sessionmaker(get_engine(), autoflush=False, expire_on_commit=False)
    return _factory


async def init_db() -> None:
    """按模型建表（幂等）。"""
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def dispose_engine() -> None:
    """进程退出时释放连接池。"""
    global _engine, _factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _factory = None
