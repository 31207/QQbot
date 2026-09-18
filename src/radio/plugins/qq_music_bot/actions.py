"""动作层：所有功能点的唯一实现，确定性指令与 LLM 工具共用。

每个动作返回 :class:`radio.actions.ActionResult`（文本 + 可选图片），
由插件负责发送；LLM 工具循环复用同一批动作，业务逻辑零重复。
"""

from __future__ import annotations

import asyncio
from typing import Callable

from nonebot import logger

from radio.actions import ActionResult
from radio.render import SOURCE_NAMES, render_page, render_records
from radio.runtime import notices, permissions, requests, search, settings, songs, state, users
from radio.services import MusicSearchError, fetch_cover
from radio.util import beijing_now

from . import texts

# ---------------------------------------------------------------- 渲染辅助


async def _fetch_covers(items: list[dict]) -> dict[str, object]:
    tasks: dict[str, object] = {}
    for item in items:
        url = item.get("cover") or ""
        if not url or url in tasks:
            continue
        tasks[url] = fetch_cover(
            settings.music_api_base,
            url,
            settings.cover_dir,
            item.get("name") or "",
            item.get("artist") or "",
        )
    if not tasks:
        return {}
    return dict(zip(tasks.keys(), await asyncio.gather(*tasks.values())))


async def _render_search(session) -> bytes | None:
    page_songs = session.page_songs(settings.page_size)
    covers = await _fetch_covers(page_songs)
    label = SOURCE_NAMES.get(session.source or "", "全部平台")
    try:
        return await asyncio.to_thread(
            render_page,
            session.query,
            label,
            page_songs,
            session.page,
            settings.page_size,
            session.total_pages,
            len(session.songs),
            covers,
        )
    except Exception:
        logger.exception("渲染搜索结果图片失败")
        return None


# ---------------------------------------------------------------- 音乐功能


async def action_search(uid: str, keyword: str, source: str | None = None) -> ActionResult:
    keyword = (keyword or "").strip()
    if not keyword:
        return ActionResult(texts.SEARCH_USAGE)
    try:
        if keyword.startswith("搜索"):
            keyword = keyword[2:].strip()
            print(keyword)
        session = await search.search(uid, keyword, source)
    except MusicSearchError as exc:
        return ActionResult(f"搜索失败：{exc}")
    if not session.songs:
        return ActionResult("没有找到相关歌曲，换个关键词试试")
    img = await _render_search(session)
    if img is None:
        return ActionResult("图片生成失败，请稍后重试")
    return ActionResult(f"已搜索「{keyword}」，返回结果图片。", img)


async def action_paginate(uid: str, direction: str) -> ActionResult:
    if direction == "exit":
        search.exit(uid)
        return ActionResult("已退出音乐搜索")
    session, err = search.paginate(uid, direction)
    if err:
        return ActionResult(err)
    img = await _render_search(session)
    if img is None:
        return ActionResult("图片生成失败，请稍后重试")
    return ActionResult("已翻页。", img)


async def action_order(uid: str, index: int) -> ActionResult:
    session = search.session(uid)
    if session is None or not session.songs:
        return ActionResult("你还没有搜索结果，先发送「搜索 歌名」搜索歌曲")
    if index < 1 or index > len(session.songs):
        return ActionResult(f"序号超出范围（1-{len(session.songs)}），请重新输入")
    info = session.songs[index - 1]
    result = await requests.order(uid, info)
    if result.ok:
        return ActionResult(
            texts.format_order_success(info, result.first, result.used, result.limit, result.period)
        )
    return ActionResult(texts.format_order_error(result.reason, info, result.period, result.limit))


async def action_order_shared(uid: str) -> ActionResult:
    info = state.pending_share(uid)
    if info is None:
        return ActionResult("没有找到待点的分享歌曲，请重新分享一次。")
    result = await requests.order(uid, info)
    state.clear_pending_share(uid)
    if result.ok:
        return ActionResult(
            texts.format_order_success(info, result.first, result.used, result.limit, result.period)
        )
    return ActionResult(texts.format_order_error(result.reason, info, result.period, result.limit))


async def action_my_songs(uid: str) -> ActionResult:
    records = await requests.list_for_user(uid, settings.record_limit)
    if not records:
        return ActionResult("你还没有点歌记录。先「搜索 歌名」搜索，再「点歌 序号」即可点歌。")
    covers = await _fetch_covers(records)
    img = await asyncio.to_thread(render_records, records, covers, len(records))
    if img is None:
        return ActionResult(texts.format_records(records))
    return ActionResult(f"已生成「我的歌单」图片（共 {len(records)} 条点歌记录），图片已发送。", img)


async def action_remaining(uid: str) -> ActionResult:
    period, limit = permissions.role_limit(uid)
    used = await requests.count(uid, period)
    return ActionResult(texts.format_remaining(used, limit, period))


async def action_my_id(uid: str) -> ActionResult:
    return ActionResult(f"你的用户ID：{uid}")


async def action_profile(uid: str) -> ActionResult:
    if permissions.is_super_admin(uid):
        role = "超级管理员"
    elif permissions.is_admin(uid):
        role = "管理员"
    else:
        role = "用户"
    period, limit = permissions.role_limit(uid)
    used = await requests.count(uid, period)
    return ActionResult(texts.format_profile(beijing_now(), uid, role, used, limit, period))


async def action_remark(uid: str, song_id: int | None, content: str = "") -> ActionResult:
    if not song_id:
        return ActionResult(
            "用法：「备注 歌曲编号 内容」设置备注；「备注 歌曲编号」清除备注\n"
            "歌曲编号见「我的歌单」每条后面的 [编号N]"
        )
    ok = await requests.set_remark(uid, song_id, content or "")
    if not ok:
        return ActionResult(f"你没有点过编号为 {song_id} 的歌曲，无法备注")
    if content:
        return ActionResult(f"已为编号 {song_id} 的歌曲添加备注：{content}")
    return ActionResult(f"已清除编号 {song_id} 的歌曲备注")


async def action_help_menu(uid: str) -> ActionResult:
    return ActionResult(texts.HELP_MENU)


# ---------------------------------------------------------------- 管理功能


async def action_ban_user(uid: str, user_id: str) -> ActionResult:
    if not permissions.is_super_admin(uid):
        return ActionResult("无权限：仅超级管理员可执行封禁/解封")
    if await users.set_banned(str(user_id), True):
        return ActionResult(f"已封禁用户 {user_id}")
    return ActionResult(f"用户 {user_id} 不存在，无法封禁")


async def action_unban_user(uid: str, user_id: str) -> ActionResult:
    if not permissions.is_super_admin(uid):
        return ActionResult("无权限：仅超级管理员可执行封禁/解封")
    if await users.set_banned(str(user_id), False):
        return ActionResult(f"已解封用户 {user_id}")
    return ActionResult(f"用户 {user_id} 不存在，无法解封")


async def action_banned_list(uid: str) -> ActionResult:
    if not permissions.is_super_admin(uid):
        return ActionResult("无权限：仅超级管理员可查看封禁列表")
    banned = await users.list_banned()
    if not banned:
        return ActionResult("当前没有被封禁的用户")
    return ActionResult("被封禁用户：" + "、".join(banned))


async def action_reset_quota(uid: str) -> ActionResult:
    if not permissions.is_admin(uid):
        return ActionResult("无权限：仅管理员可重置点歌次数")
    n = await requests.reset_all()
    return ActionResult(f"已重置所有人的点歌次数（清零 {n} 条记录）")


async def action_notice_status(uid: str) -> ActionResult:
    if not permissions.is_admin(uid):
        return ActionResult("无权限：仅管理员可查看通知发送情况")
    pending, sent_count, failed = await notices.status()
    return ActionResult(texts.format_notice_status(pending, sent_count, failed))


async def action_ban_song(uid: str, target: str) -> ActionResult:
    if not permissions.is_admin(uid):
        return ActionResult("无权限：仅管理员可禁播歌曲")
    if str(target).isdigit():
        ok = await songs.set_banned(int(target), True)
        return ActionResult(f"已禁播歌曲 #{target}" if ok else f"歌曲 #{target} 不存在，无法禁播")
    n = await songs.set_banned_by_name(str(target), True)
    return ActionResult(f"已禁播 {n} 首匹配《{target}》的歌曲")


async def action_unban_song(uid: str, target: str) -> ActionResult:
    if not permissions.is_admin(uid):
        return ActionResult("无权限：仅管理员可解禁歌曲")
    if str(target).isdigit():
        ok = await songs.set_banned(int(target), False)
        return ActionResult(f"已解禁歌曲 #{target}" if ok else f"歌曲 #{target} 不存在，无法解禁")
    n = await songs.set_banned_by_name(str(target), False)
    return ActionResult(f"已解禁 {n} 首匹配《{target}》的歌曲")


# ---------------------------------------------------------------- LLM 工具映射


def _handler(fn: Callable, *names: str, casts: dict[str, Callable] | None = None):
    """把 (uid, **params) 动作包成 LLM 工具处理器 (uid, params_dict)。"""

    async def wrapper(uid: str, params: dict) -> ActionResult:
        kwargs: dict = {}
        for name in names:
            value = params.get(name)
            if value is not None and casts and name in casts:
                value = casts[name](value)
            kwargs[name] = value
        return await fn(uid, **kwargs)

    return wrapper


TOOL_HANDLERS = {
    "search_songs": _handler(action_search, "query", "source"),
    "order_song": _handler(action_order, "index", casts={"index": int}),
    "my_song_list": _handler(action_my_songs),
    "remaining_quota": _handler(action_remaining),
    "my_user_id": _handler(action_my_id),
    "my_profile": _handler(action_profile),
    "add_remark": _handler(action_remark, "song_id", "content", casts={"song_id": int}),
    "help_menu": _handler(action_help_menu),
    "ban_user": _handler(action_ban_user, "user_id", casts={"user_id": str}),
    "unban_user": _handler(action_unban_user, "user_id", casts={"user_id": str}),
    "reset_quota": _handler(action_reset_quota),
    "ban_song": _handler(action_ban_song, "target", casts={"target": str}),
    "unban_song": _handler(action_unban_song, "target", casts={"target": str}),
    "banned_list": _handler(action_banned_list),
    "order_shared_song": _handler(action_order_shared),
}
