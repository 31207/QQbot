"""组合根：装配进程级单例（仅 bot 进程使用）。

插件只从这里拿实例，业务类本身保持可注入（测试时用自定义 session_factory）。
"""

from __future__ import annotations

from qqbot.config import settings
from qqbot.services.notices import NoticeService
from qqbot.services.permissions import Permissions
from qqbot.services.requests import RequestService
from qqbot.services.search import MusicAPI, SearchService
from qqbot.services.songs import SongService
from qqbot.services.users import UserService
from qqbot.state import StateStore

__all__ = [
    "notices",
    "permissions",
    "requests",
    "search",
    "settings",
    "songs",
    "state",
    "users",
]

state = StateStore(
    session_ttl=settings.session_ttl,
    memory_ttl=settings.llm_memory_ttl,
    memory_turns=settings.llm_memory_turns,
)

permissions = Permissions(
    settings.permissions_file,
    week_limit=settings.week_limit,
    admin_daily_limit=settings.admin_daily_limit,
)

songs = SongService()
users = UserService()
requests = RequestService(songs, users, permissions)
search = SearchService(MusicAPI(settings.music_api_base), state, settings.page_size)
notices = NoticeService()
