"""Go Music API 搜索客户端。"""

from __future__ import annotations

import httpx

SEARCH_TIMEOUT = 15.0


class MusicSearchError(Exception):
    pass


class MusicAPI:
    def __init__(self, base: str):
        self.base = (base or "").rstrip("/")

    async def search_songs(
        self, query: str, sources: list[str] | None = None
    ) -> list[dict]:
        params: dict = {"q": query, "type": "song"}
        if sources:
            params["sources"] = sources
        try:
            async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT) as client:
                resp = await client.get(
                    f"{self.base}/api/v1/music/search", params=params
                )
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
