import nonebot

nonebot.init()

import os

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from radio.db.models import Base
from radio.services.permissions import Permissions
from radio.services.requests import RequestService
from radio.services.songs import SongService
from radio.services.users import UserService

# 测试库连接串：默认本地 qqbot_test（密码经 PGPASSWORD 环境变量提供）；
# 也可用 TEST_DATABASE_URL 覆盖，例如 CI 里的 postgres 服务。
_TEST_URL = os.environ.get("TEST_DATABASE_URL") or (
    "postgresql+asyncpg://qqbot_admin@127.0.0.1:5432/qqbot_test"
)


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine(_TEST_URL)
    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS song_selected_notice CASCADE"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(db_engine):
    return async_sessionmaker(db_engine, autoflush=False, expire_on_commit=False)


@pytest_asyncio.fixture
async def permissions(tmp_path):
    path = tmp_path / "permissions.json"
    return Permissions(path, week_limit=5, admin_daily_limit=99)


@pytest_asyncio.fixture
async def services(session_factory, permissions):
    songs = SongService(session_factory)
    users = UserService(session_factory)
    requests = RequestService(songs, users, permissions, session_factory)
    return songs, users, requests


def song_info(source="qq", sid="001", name="晴天", artist="周杰伦"):
    return {
        "source": source,
        "id": sid,
        "name": name,
        "artist": artist,
        "album": "",
        "cover": "",
        "duration": 269,
        "url": "",
        "link": "",
    }
