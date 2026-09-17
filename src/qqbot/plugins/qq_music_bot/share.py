"""从 OneBot 消息段提取音乐分享卡片信息（adapter 相关逻辑只存在于插件层）。"""

from __future__ import annotations

import json
import re

from nonebot.adapters.onebot.v11 import MessageEvent


def _extract_songmid(text: str) -> str:
    if not text:
        return ""
    m = re.search(r"[?&]songmid=([0-9A-Za-z]+)", text)
    return m.group(1) if m else ""


def _from_json_segment(raw: str) -> dict | None:
    try:
        payload = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    meta = payload.get("meta") or {}
    music = meta.get("music") if isinstance(meta, dict) else {}
    is_music_share = (
        payload.get("view") == "music"
        or bool(music)
        or str(payload.get("desc", "")) == "音乐"
        or "[分享]" in str(payload.get("prompt", ""))
    )
    if not is_music_share:
        return None
    title = (music.get("title") or "").strip() if isinstance(music, dict) else ""
    artist = (music.get("desc") or "").strip() if isinstance(music, dict) else ""
    url = ((music.get("music_url") or music.get("jump_url")) or "").strip() if isinstance(music, dict) else ""
    if not title:
        title = str(payload.get("prompt", "") or "").replace("[分享]", "").strip()
    song_id = str((music.get("id") or "") if isinstance(music, dict) else "")
    if not song_id:
        song_id = _extract_songmid(url)
    cover = (music.get("preview") or "").strip() if isinstance(music, dict) else ""
    return {
        "title": title,
        "artist": artist,
        "url": url,
        "source": "qq",
        "id": song_id,
        "cover": cover,
        "detail": json.dumps(
            {"prompt": payload.get("prompt", ""), "msg": payload.get("msg", ""), "meta": meta},
            ensure_ascii=False,
            default=str,
        )[:500],
    }


def extract_share(event: MessageEvent) -> dict | None:
    """返回 {title, artist, url, source, id, cover, detail} 或 None。"""
    for seg in event.message:
        seg_type = seg.type
        data = dict(seg.data or {})
        if seg_type == "music":
            return {
                "title": (data.get("title") or "").strip(),
                "artist": (data.get("content") or "").strip(),
                "url": (data.get("url") or "").strip(),
                "source": (data.get("type") or "").strip(),
                "id": str(data.get("id") or ""),
                "cover": (data.get("image") or "").strip(),
                "detail": json.dumps(data, ensure_ascii=False)[:300],
            }
        if seg_type == "json":
            share = _from_json_segment(data.get("data"))
            if share is not None:
                return share
        if seg_type == "xml":
            raw = data.get("data") if isinstance(data, dict) else ""
            if raw and ("[分享]" in str(raw) or "music" in str(raw).lower()):
                return {
                    "title": "",
                    "artist": "",
                    "url": "",
                    "source": "",
                    "id": "",
                    "cover": "",
                    "detail": str(raw)[:200],
                }
    return None


def to_song_info(share: dict) -> dict:
    """分享信息 → 点歌服务所需的歌曲信息字典。"""
    return {
        "source": str(share.get("source") or "qq"),
        "id": str(share.get("id") or ""),
        "name": str(share.get("title") or ""),
        "artist": str(share.get("artist") or ""),
        "album": "",
        "cover": str(share.get("cover") or ""),
        "duration": 0,
        "url": str(share.get("url") or ""),
        "link": "",
    }
