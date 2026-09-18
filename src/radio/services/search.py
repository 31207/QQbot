"""Go Music API 搜索客户端 + 搜索会话服务。"""

from __future__ import annotations

import math

import httpx

from radio.state import SearchSession, StateStore

SEARCH_TIMEOUT = 15.0


class MusicSearchError(Exception):
    pass


class MusicAPI:
    def __init__(self, base: str, timeout: float = SEARCH_TIMEOUT) -> None:
        self.base = (base or "").rstrip("/")
        self.timeout = timeout

    async def search(self, query: str, sources: list[str] | None = None) -> list[dict]:
        params: dict = {"q": query, "type": "song"}
        if sources:
            params["sources"] = sources
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(f"{self.base}/api/v1/music/search", params=params)
        except httpx.HTTPError as exc:
            raise MusicSearchError(f"无法连接搜索接口：{exc}") from exc
        if resp.status_code != 200:
            raise MusicSearchError(f"搜索接口返回 HTTP {resp.status_code}")
        try:
            body = resp.json()
        except ValueError as exc:
            raise MusicSearchError("搜索接口返回了无效的 JSON") from exc
        if body.get("code") != 200:
            raise MusicSearchError(str(body.get("msg") or "搜索失败"))
        return (body.get("data") or {}).get("songs") or []


class SearchService:
    """搜索 + 会话/翻页管理（会话状态存在 StateStore，带 TTL）。"""

    def __init__(self, api: MusicAPI, state: StateStore, page_size: int = 10) -> None:
        self.api = api
        self.state = state
        self.page_size = page_size

    async def search(self, uid: str, keyword: str, source: str | None = None) -> SearchSession:
        songs = await self.api.search(keyword, [source] if source else None)
        session = SearchSession(
            query=keyword,
            source=source,
            songs=songs,
            page=1,
            total_pages=math.ceil(len(songs) / self.page_size) if songs else 1,
        )
        self.state.set_search(uid, session)
        return session

    def session(self, uid: str) -> SearchSession | None:
        return self.state.search_session(uid)

    def paginate(self, uid: str, direction: str) -> tuple[SearchSession | None, str | None]:
        """翻页（prev / next）；返回 (会话, 错误文案或 None)。"""
        session = self.state.search_session(uid)
        if session is None:
            return None, "当前没有进行中的搜索，先发送「搜索 歌名」开始搜索"
        if direction == "prev":
            if session.page <= 1:
                return session, "已经是第一页了"
            session.page -= 1
        else:
            if session.page >= session.total_pages:
                return session, "已经是最后一页了"
            session.page += 1
        return session, None

    def exit(self, uid: str) -> None:
        self.state.clear_search(uid)
