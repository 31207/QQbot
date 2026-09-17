"""业务服务层。"""

from qqbot.services.covers import fetch_cover
from qqbot.services.notices import NoticeService
from qqbot.services.permissions import Permissions
from qqbot.services.requests import OrderResult, RequestService
from qqbot.services.search import MusicAPI, MusicSearchError, SearchService
from qqbot.services.songs import SongService
from qqbot.services.users import UserService

__all__ = [
    "MusicAPI",
    "MusicSearchError",
    "NoticeService",
    "OrderResult",
    "Permissions",
    "RequestService",
    "SearchService",
    "SongService",
    "UserService",
    "fetch_cover",
]
