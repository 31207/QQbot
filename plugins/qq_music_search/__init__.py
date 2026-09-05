"""音乐搜索插件（NoneBot2 / OneBot v11，仅私聊）。

指令（@机器人 或私聊直接发）：
- 「搜索 晴天」            全平台搜索
- 「搜索 qq 晴天」         指定平台搜索
- 「上一页」/「下一页」    翻页
- 「退出搜索」            结束搜索
"""

from __future__ import annotations

import asyncio
import math
import re
import time
from pathlib import Path

from nonebot import get_driver, logger, on_message
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, MessageSegment
from nonebot.rule import Rule, to_me

from .api import MusicAPI, MusicSearchError
from .covers import fetch_cover
from .render import SOURCE_NAMES, render_page, render_records

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _env(name: str, default: str = "") -> str:
    """从 NoneBot 配置读取（含 .env / .env.prod / 环境变量），未设置用默认值。"""
    value = getattr(get_driver().config, name.lower(), None)
    if value is None or not str(value).strip():
        return default
    return str(value).strip()


API = MusicAPI(_env("QQ_MUSIC_API_BASE", "http://127.0.0.1:8080"))
PAGE_SIZE = int(_env("QQ_MUSIC_PAGE_SIZE", "10") or "10")
COVER_DIR = Path(
    _env("QQ_MUSIC_COVER_DIR") or str(_PROJECT_ROOT / "data" / "covers")
)
SESSION_TTL = int(_env("QQ_MUSIC_SESSION_TTL", "600") or "600")

PLATFORM_ALIASES = {
    "netease": ("netease", "网易云", "网易云音乐", "网易"),
    "qq": ("qq", "qq音乐", "腾讯"),
    "kugou": ("kugou", "酷狗"),
    "kuwo": ("kuwo", "酷我"),
    "migu": ("migu", "咪咕"),
    "jamendo": ("jamendo",),
    "joox": ("joox",),
    "qianqian": ("qianqian", "千千", "千千静听"),
    "soda": ("soda", "汽水", "汽水音乐"),
    "bilibili": ("bilibili", "b站", "哔哩哔哩"),
}
_ALIAS_TO_SOURCE = {a: s for s, aliases in PLATFORM_ALIASES.items() for a in aliases}

_sessions: dict[str, dict] = {}

_USAGE = (
    "用法：\n"
    "「搜索 歌名」全平台搜索；「搜索 平台 歌名」指定平台\n"
    "例如：搜索 晴天 / 搜索 qq 晴天\n"
    "支持平台：网易云、QQ音乐、酷狗、酷我、咪咕、汽水、千千、JOOX、Jamendo、B站"
)


def _active_session(user_id: str) -> dict | None:
    sess = _sessions.get(user_id)
    if not sess:
        return None
    if time.time() - sess["ts"] > SESSION_TTL:
        _sessions.pop(user_id, None)
        return None
    sess["ts"] = time.time()
    return sess


def get_last_search(user_id: str) -> dict | None:
    """供其他插件读取用户最近一次搜索会话（含 songs 列表）。"""
    return _active_session(user_id)


def fetch_cached_cover(cover_url: str, name: str = "", artist: str = ""):
    """供其他插件复用封面缓存下载（经 /api/v1/music/cover 代理并落盘缓存）。"""
    return fetch_cover(API.base, cover_url, COVER_DIR, name, artist)


def parse_search_command(text: str) -> tuple[str | None, str] | None:
    """「搜索 [平台] 关键词」→ (平台, 关键词)；非搜索指令返回 None。"""
    t = (text or "").lstrip("/").strip()
    if not t.startswith("搜索"):
        return None
    rest = t[2:].strip()
    parts = rest.split(maxsplit=1)
    if parts and parts[0].lower() in _ALIAS_TO_SOURCE:
        source = _ALIAS_TO_SOURCE[parts[0].lower()]
        keyword = parts[1].strip() if len(parts) > 1 else ""
        return source, keyword
    return None, rest


async def _is_private(event: MessageEvent) -> bool:
    return event.message_type == "private"


def _is_search_related(event: MessageEvent) -> bool:
    text = event.get_plaintext().strip()
    t = text.lstrip("/").strip()
    if t.startswith("搜索"):
        return True
    return re.sub(r"\s+", "", t) in ("上一页", "下一页", "退出搜索")


matcher = on_message(
    priority=1,
    block=True,
    rule=to_me() & Rule(_is_private) & Rule(_is_search_related),
)


async def _render_session(sess: dict) -> bytes | None:
    songs: list[dict] = sess["songs"]
    page: int = sess["page"]
    page_songs = songs[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]

    tasks: dict[str, object] = {}
    for s in page_songs:
        url = s.get("cover") or ""
        if not url or url in tasks:
            continue
        tasks[url] = fetch_cover(
            API.base,
            url,
            COVER_DIR,
            s.get("name") or "",
            s.get("artist") or "",
        )
    covers: dict[str, object] = {}
    if tasks:
        covers = dict(zip(tasks.keys(), await asyncio.gather(*tasks.values())))

    source_label = SOURCE_NAMES.get(sess.get("source") or "", "全部平台")
    try:
        return await asyncio.to_thread(
            render_page,
            sess["query"],
            source_label,
            page_songs,
            page,
            PAGE_SIZE,
            sess["total_pages"],
            len(songs),
            covers,
        )
    except Exception:
        logger.exception("渲染搜索结果图片失败")
        return None


@matcher.handle()
async def _(bot: Bot, event: MessageEvent):
    user_id = event.get_user_id()
    text = event.get_plaintext().strip()
    compact = re.sub(r"\s+", "", text)

    if compact == "退出搜索":
        _sessions.pop(user_id, None)
        await matcher.finish("已退出音乐搜索")

    sess = _active_session(user_id)
    if compact in ("上一页", "下一页"):
        if not sess:
            await matcher.finish("当前没有进行中的搜索，先发送「搜索 歌名」开始搜索")
        if compact == "上一页":
            if sess["page"] <= 1:
                await matcher.finish("已经是第一页了")
            sess["page"] -= 1
        else:
            if sess["page"] >= sess["total_pages"]:
                await matcher.finish("已经是最后一页了")
            sess["page"] += 1
        img = await _render_session(sess)
        if img is None:
            await matcher.finish("图片生成失败，请稍后重试")
        await matcher.finish(MessageSegment.image(img))

    parsed = parse_search_command(text)
    if parsed is None:
        await matcher.finish()
    source, keyword = parsed
    if not keyword:
        await matcher.finish(_USAGE)

    await matcher.send("正在搜索，请稍候…")
    try:
        songs = await API.search_songs(keyword, [source] if source else None)
    except MusicSearchError as exc:
        await matcher.finish(f"搜索失败：{exc}")
    if not songs:
        await matcher.finish("没有找到相关歌曲，换个关键词试试")

    _sessions[user_id] = {
        "query": keyword,
        "source": source,
        "songs": songs,
        "page": 1,
        "total_pages": math.ceil(len(songs) / PAGE_SIZE),
        "ts": time.time(),
    }
    img = await _render_session(_sessions[user_id])
    if img is None:
        await matcher.finish("图片生成失败，请稍后重试")
    await matcher.finish(MessageSegment.image(img))
