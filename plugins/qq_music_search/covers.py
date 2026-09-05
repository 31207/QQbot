"""封面拉取与本地磁盘缓存（通过 API 的封面代理绕过防盗链）。"""

from __future__ import annotations

import asyncio
import hashlib
import io
from pathlib import Path

import httpx
from PIL import Image

_COVER_TIMEOUT = 12.0


def _hash_key(url: str) -> str:
    return hashlib.md5(url.encode("utf-8")).hexdigest()


def get_cache_path(cache_dir: Path, url: str) -> Path:
    return cache_dir / f"{_hash_key(url)}.jpg"


async def _load_image(data: bytes) -> Image.Image | None:
    def _load() -> Image.Image | None:
        try:
            with Image.open(io.BytesIO(data)) as img:
                img.load()
                return img.convert("RGB")
        except Exception:
            return None

    return await asyncio.to_thread(_load)


async def fetch_cover(
    api_base: str,
    cover_url: str,
    cache_dir: Path,
    name: str = "",
    artist: str = "",
) -> Image.Image | None:
    """取封面：先查本地缓存，未命中则经 /api/v1/music/cover 代理下载并落盘。"""
    if not cover_url:
        return None
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = get_cache_path(cache_dir, cover_url)

    if path.exists() and path.stat().st_size > 0:
        img = await _load_image(path.read_bytes())
        if img is not None:
            return img
        path.unlink(missing_ok=True)

    params = {"url": cover_url, "name": name, "artist": artist}
    try:
        async with httpx.AsyncClient(
            timeout=_COVER_TIMEOUT, follow_redirects=True
        ) as client:
            resp = await client.get(f"{api_base}/api/v1/music/cover", params=params)
        if resp.status_code != 200 or not resp.content:
            return None
        img = await _load_image(resp.content)
        if img is None:
            return None
        path.write_bytes(resp.content)
        return img
    except httpx.HTTPError:
        return None
