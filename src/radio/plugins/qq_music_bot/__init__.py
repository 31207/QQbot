"""校园广播站 QQ 点歌机器人（单一业务插件，多通道：OneBot V11 / 官方 QQ C2C / 频道私信）。

消息处理顺序（业务分发与 adapter 无关，收发统一走 Channel）：
1. 歌曲分享卡片（仅 OneBot 有 music/json/xml 段）→ 精确搜索 + 待确认点歌；
2. 管理指令（封禁/解封/封禁列表/重置/禁歌）——先于封禁拦截，保证管理员可自解封；
3. 封禁拦截；
4. 状态流转（帮助菜单选号 / 一次性点歌·搜索模式 / 分享确认）；
5. 确定性指令 → 动作层执行（LLM 开启时用其措辞，失败自动回退原文）；
6. LLM 兜底处理自然语言；未开启 LLM 时非指令消息静默忽略。

后台任务：会话状态回收（防内存泄漏）。

注意：不同通道的用户标识不同，业务 ID 统一带平台前缀
（onebot:QQ号 / c2c:user_openid / dms:guild_id:频道用户id）；
封禁、白名单等涉及用户 ID 的功能需按对应通道的带前缀 ID 配置（「ID」指令可查看）。
"""

from __future__ import annotations

import asyncio

from nonebot import get_driver, logger, on_message, on_notice
from nonebot.adapters.onebot.v11 import Bot, FriendAddNoticeEvent, MessageEvent
from nonebot.adapters.qq import Bot as QQBot
from nonebot.adapters.qq import C2CMessageCreateEvent, DirectMessageCreateEvent
from nonebot.rule import Rule, to_me

from radio.actions import ActionResult
from radio.db import dispose_engine, init_db
from radio.runtime import requests, settings, state, users
from radio.services.llm import LLMService
from radio.util import compact

from . import actions, channels, texts
from .channels import Channel
from .commands import ADMIN_KINDS, Command, CommandKind, parse_command
from .share import extract_share, to_song_info

llm = LLMService(settings, actions.TOOL_HANDLERS)
driver = get_driver()

async def _is_private(event: MessageEvent) -> bool:
    return event.message_type == "private"


async def _is_qq_c2c(event) -> bool:
    return isinstance(event, C2CMessageCreateEvent)


async def _is_qq_dms(event) -> bool:
    return isinstance(event, DirectMessageCreateEvent)


def _is_friend_add(event) -> bool:
    return isinstance(event, FriendAddNoticeEvent)


onebot_matcher = on_message(priority=1, block=True, rule=to_me() & Rule(_is_private))
qq_matcher = on_message(priority=1, block=True, rule=Rule(_is_qq_c2c))
qq_dms_matcher = on_message(priority=1, block=True, rule=Rule(_is_qq_dms))
friend_add_matcher = on_notice(priority=1, block=True, rule=Rule(_is_friend_add))

_CONFIRM_WORDS = {"要", "好", "点", "可以", "同意", "嗯", "行", "OK", "ok", "Ok"}


# ---------------------------------------------------------------- 发送辅助


async def send_result(channel: Channel, result: ActionResult, phrase: str | None = None) -> None:
    if result.media is not None:
        await channel.send_image(result.media)
    text = result.summary
    if text and phrase is not None and llm.enabled:
        text = await llm.phrase(phrase, text)
    if text:
        await channel.send_text(text)


# ---------------------------------------------------------------- 消息分发


@onebot_matcher.handle()
async def _(bot: Bot, event: MessageEvent):
    channel = channels.from_onebot(bot, event)
    await dispatch(channel, event.get_plaintext(), extract_share(event))


@qq_matcher.handle()
async def _(bot: QQBot, event: C2CMessageCreateEvent):
    channel = channels.from_qq_c2c(bot, event)
    await dispatch(channel, event.get_plaintext(), None)


@qq_dms_matcher.handle()
async def _(bot: QQBot, event: DirectMessageCreateEvent):
    channel = channels.from_qq_dms(bot, event)
    await dispatch(channel, event.get_plaintext(), None)


async def dispatch(channel: Channel, raw_text: str, share: dict | None) -> None:
    uid = channel.user_id
    text = (raw_text or "").strip()
    user_state = state.user(uid)

    # 1) 歌曲分享卡片（仅 OneBot 通道有）
    if share is not None:
        await handle_share(channel, uid, user_state, share)
        return

    cmd = parse_command(text)

    # 2) 管理指令（先于封禁拦截）
    if cmd is not None and cmd.kind in ADMIN_KINDS:
        await run_admin_command(channel, uid, cmd)
        return
    t = (text or "").lstrip("/").strip()
    if t.startswith("封禁") or t.startswith("解封"):
        await channel.send_text("用法：「封禁 用户ID」/「解封 用户ID」，仅超级管理员可用")
        return

    # 3) 封禁拦截
    if await users.is_banned(uid):
        await channel.send_text("你已被封禁，无法使用点歌功能")
        return

    # 4) 状态流转
    if user_state.help_pending:
        user_state.help_pending = False
        if await handle_help_choice(channel, uid, user_state, text):
            return

    if user_state.pending_mode:
        mode = user_state.pending_mode
        user_state.pending_mode = None
        if mode == "song" and text.strip().isdigit():
            await do_order(channel, uid, text, int(text.strip()))
            return
        if mode == "search" and text:
            await do_search(channel, uid, text, None)
            return

    if user_state.pending_order:
        user_state.pending_order = False
        if text.isdigit() or compact(text) in _CONFIRM_WORDS:
            idx = int(text) if text.isdigit() else 1
            await do_order(channel, uid, text, idx)
            return

    # 5) 确定性指令
    if cmd is not None:
        await run_command(channel, uid, user_state, cmd, text)
        return

    # 6) LLM 兜底
    if llm.enabled and text:
        await llm_fallback(channel, uid, text)


async def handle_share(channel: Channel, uid: str, user_state, share: dict) -> None:
    if not share.get("title"):
        await channel.send_text(
            "人，咪看到你发来的音乐卡片了，但没能认出是哪首歌。"
            "你可以直接把「搜索 歌名」发给咪，或发「点歌 序号」哦。"
        )
        return
    state.set_pending_share(uid, to_song_info(share))
    query = await llm.share_query(share)
    await channel.send_text("正在搜索，请稍候…")
    result = await actions.action_search(uid, query, None)
    if result.media is not None:
        await channel.send_image(result.media)
        user_state.pending_order = True
        await channel.send_text(
            "咪帮你搜到啦，上面哪首是你想点的？回复「序号」点这首歌，或者回复「要」默认点第一条。"
        )
    else:
        await channel.send_text(
            result.summary or "没搜到这首歌，换个关键词或直接「搜索 歌名」试试。"
        )


async def do_search(channel: Channel, uid: str, raw_text: str, source: str | None) -> None:
    await channel.send_text("正在搜索，请稍候…")
    result = await actions.action_search(uid, raw_text, source)
    await send_result(channel, result, phrase=raw_text)


async def do_order(channel: Channel, uid: str, raw_text: str, index: int) -> None:
    result = await actions.action_order(uid, index)
    await send_result(channel, result, phrase=raw_text)


async def handle_help_choice(channel: Channel, uid: str, user_state, text: str) -> bool:
    key = text.strip().lstrip("/")
    if key == "3":
        await send_result(channel, await actions.action_my_songs(uid))
        return True
    if key == "4":
        result = await actions.action_remaining(uid)
        await channel.send_text(result.summary)
        return True
    detail = texts.HELP_DETAILS.get(key)
    if detail is None:
        return False
    if key == "1":
        user_state.pending_mode = "song"
        await channel.send_text(
            detail + "\n\n已开启点歌模式：直接回复数字序号即可点歌；也可继续用「点歌 序号」。"
        )
    elif key == "2":
        user_state.pending_mode = "search"
        await channel.send_text(
            detail + "\n\n已开启搜索模式：直接发送歌名即可搜索；也可继续用「搜索 歌名」。"
        )
    else:
        await channel.send_text(detail + "\n\n该功能已开启，按上方说明使用。")
    return True


async def run_command(channel: Channel, uid: str, user_state, cmd: Command, raw_text: str) -> None:
    kind = cmd.kind

    if kind == CommandKind.SEARCH:
        source, keyword = cmd.args
        if not keyword:
            await channel.send_text(texts.SEARCH_USAGE)
            return
        await do_search(channel, uid, raw_text, source)
        return

    if kind in (CommandKind.SEARCH_NEXT, CommandKind.SEARCH_PREV, CommandKind.SEARCH_EXIT):
        direction = {
            CommandKind.SEARCH_NEXT: "next",
            CommandKind.SEARCH_PREV: "prev",
            CommandKind.SEARCH_EXIT: "exit",
        }[kind]
        await send_result(channel, await actions.action_paginate(uid, direction))
        return

    if kind == CommandKind.ORDER:
        index = cmd.args[0]
        if index is None:
            await channel.send_text(
                "用法：先「搜索 歌名」搜索歌曲，再「点歌 序号」点选结果，例如：点歌 3"
            )
            return
        await do_order(channel, uid, raw_text, index)
        return

    if kind == CommandKind.MY_SONGS:
        await send_result(channel, await actions.action_my_songs(uid), phrase=raw_text)
        return

    if kind == CommandKind.REMAINING:
        await send_result(channel, await actions.action_remaining(uid), phrase=raw_text)
        return

    if kind == CommandKind.MY_SELECTIONS:
        await send_result(channel, await actions.action_my_selections(uid), phrase=raw_text)
        return

    if kind == CommandKind.MY_ID:
        await send_result(channel, await actions.action_my_id(uid))
        return

    if kind == CommandKind.PROFILE:
        await send_result(channel, await actions.action_profile(uid))
        return

    if kind == CommandKind.REMARK:
        song_id, content = cmd.args
        if song_id is None:
            await channel.send_text(
                "用法：「备注 歌曲编号 内容」设置备注；「备注 歌曲编号」清除备注\n"
                "歌曲编号见「我的歌单」每条后面的 [编号N]"
            )
            return
        await send_result(
            channel, await actions.action_remark(uid, song_id, content or ""), phrase=raw_text
        )
        return

    if kind == CommandKind.HELP:
        user_state.help_pending = True
        await channel.send_text(texts.HELP_MENU)
        return


async def run_admin_command(channel: Channel, uid: str, cmd: Command) -> None:
    kind = cmd.kind
    if kind == CommandKind.BAN_USER:
        result = await actions.action_ban_user(uid, cmd.args[0])
    elif kind == CommandKind.UNBAN_USER:
        result = await actions.action_unban_user(uid, cmd.args[0])
    elif kind == CommandKind.BAN_LIST:
        result = await actions.action_banned_list(uid)
    elif kind == CommandKind.BAN_SONG:
        result = await actions.action_ban_song(uid, cmd.args[0])
    elif kind == CommandKind.UNBAN_SONG:
        result = await actions.action_unban_song(uid, cmd.args[0])
    else:  # RESET_QUOTA
        result = await actions.action_reset_quota(uid)
    await send_result(channel, result)


async def llm_fallback(channel: Channel, uid: str, text: str) -> None:
    state.push_memory(uid, "user", text)
    history = state.memory(uid)
    try:
        reply = await llm.run_tools(
            uid, history, emit=lambda media: channel.send_image(media)
        )
    except Exception:
        logger.exception("LLM 助手处理消息失败")
        reply = await llm.error_hint()
    if reply:
        await channel.send_text(reply)
        state.push_memory(uid, "assistant", reply)


# ---------------------------------------------------------------- 新好友欢迎（仅 OneBot）


@friend_add_matcher.handle()
async def _(bot: Bot, event: FriendAddNoticeEvent):
    try:
        welcome = await llm.welcome()
        await bot.call_api(
            "send_private_msg",
            user_id=event.user_id,
            message=welcome + "\n\n" + texts.FUNCTION_LIST,
        )
    except Exception:
        logger.exception("发送新好友欢迎词失败")


# ---------------------------------------------------------------- 后台维护（防内存泄漏）


async def _maintenance_loop() -> None:
    while True:
        await asyncio.sleep(60)
        state.sweep()
        requests.sweep_locks()


# ---------------------------------------------------------------- 生命周期


_tasks: list[asyncio.Task] = []


@driver.on_startup
async def _on_startup() -> None:
    await init_db()
    _tasks.append(asyncio.create_task(_maintenance_loop()))


@driver.on_shutdown
async def _on_shutdown() -> None:
    for task in _tasks:
        task.cancel()
    await dispose_engine()
