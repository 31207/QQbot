"""点歌插件（NoneBot2 / OneBot v11，仅私聊）。

流程：「搜索 歌名」得到结果图 →「点歌 序号」选取歌曲：
- 按 (source, id) 查找歌曲库，不存在则入库（is_banned=0、play_count=0）
- 已 ban → 报错；超每日上限 → 报错
- 用户不存在则创建；重复点歌则记录置顶且当日次数照扣
- 「我的歌单」等以图片展示点歌记录（含封面/编号/备注）
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from nonebot import get_driver, get_loaded_plugins, logger, on_message, on_notice
from nonebot.adapters.onebot.v11 import (
    Bot,
    FriendAddNoticeEvent,
    MessageEvent,
    MessageSegment,
)
from nonebot.rule import Rule, to_me

from .song_core import (
    HELP_DETAILS,
    HELP_MENU,
    format_records,
    format_remaining,
    is_ban_list_command,
    is_reset_command,
    match_command,
    parse_ban_command,
    parse_ban_song_command,
    parse_remark_command,
    parse_request_command,
)
from .storage import SongRequestStore

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # 项目根目录


def _env(name: str, default: str = "") -> str:
    """从 NoneBot 配置读取（含 .env / .env.prod / 环境变量），未设置用默认值。"""
    value = getattr(get_driver().config, name.lower(), None)
    if value is None or not str(value).strip():
        return default
    return str(value).strip()


_data_file = _env("QQ_SONG_DATA_FILE") or str(
    _PROJECT_ROOT / "data" / "song_requests.db"
)
STORE = SongRequestStore(_data_file)
DAILY_LIMIT = int(_env("QQ_SONG_DAILY_LIMIT", "5") or "5")
RECORD_LIMIT = int(_env("QQ_SONG_RECORD_LIMIT", "20") or "20")
SUPERUSERS: set[str] = get_driver().config.superusers

# ---------------- 权限白名单（三级：用户 / 管理员 / 超级管理员） ----------------
# 权限只能从 data/permissions.json 添加，无法在机器人端获取。
PERMISSIONS_FILE = Path(
    _env("QQ_PERMISSIONS_FILE") or str(_PROJECT_ROOT / "data" / "permissions.json")
)
_permissions: dict = {"admins": [], "super_admins": []}
_permissions_mtime: float = -1.0


def _load_permissions() -> None:
    global _permissions, _permissions_mtime
    try:
        mtime = (
            PERMISSIONS_FILE.stat().st_mtime if PERMISSIONS_FILE.exists() else -1.0
        )
        if mtime == _permissions_mtime:
            return
        data = (
            json.loads(PERMISSIONS_FILE.read_text(encoding="utf-8"))
            if PERMISSIONS_FILE.exists()
            else {}
        )
        _permissions = {
            "admins": [str(x) for x in data.get("admins", [])],
            "super_admins": [str(x) for x in data.get("super_admins", [])],
        }
        _permissions_mtime = mtime
    except Exception:
        logger.exception("读取权限白名单失败")
        _permissions = {"admins": [], "super_admins": []}
        _permissions_mtime = -1.0


def is_admin(user_id: str) -> bool:
    _load_permissions()
    return (
        user_id in _permissions["admins"]
        or user_id in _permissions["super_admins"]
    )


def is_super_admin(user_id: str) -> bool:
    _load_permissions()
    return user_id in _permissions["super_admins"]


def _find_search_plugin():
    for plugin in get_loaded_plugins():
        if plugin.name == "qq_music_search" and plugin.module:
            return plugin.module
    return None


def _find_llm_plugin():
    for plugin in get_loaded_plugins():
        if plugin.name == "llm_assist" and plugin.module:
            return plugin.module
    return None


def get_last_search(user_id: str) -> dict | None:
    """通过 NoneBot 插件管理器定位搜索插件实例（避免重复 import 导致状态不一致）。"""
    module = _find_search_plugin()
    if module is None or not hasattr(module, "get_last_search"):
        return None
    return module.get_last_search(user_id)


async def _is_private(event: MessageEvent) -> bool:
    return event.message_type == "private"


matcher = on_message(priority=5, block=True, rule=to_me() & Rule(_is_private))

# 用户临时状态：正在从帮助菜单选编号 / 已开启的功能模式("song" / "search")
_help_user: set[str] = set()
_pending_mode: dict[str, str] = {}


def _is_friend_add(event) -> bool:
    return isinstance(event, FriendAddNoticeEvent)


friend_add_matcher = on_notice(priority=1, block=True, rule=Rule(_is_friend_add))


@friend_add_matcher.handle()
async def _(bot: Bot, event: FriendAddNoticeEvent):
    """新好友添加后：不再发帮助菜单，改为 LLM 欢迎词 + 功能清单。"""
    try:
        llm = _find_llm_plugin()
        if llm is not None and hasattr(llm, "welcome_message"):
            text = await llm.welcome_message(str(event.user_id))
        else:
            text = (
                "人，你好呀！咪是校园广播站的点歌小助猫。\n\n"
                "—— 你可以这样点歌 ——\n"
                "· 最方便：直接分享一首歌给我，咪帮你搜出来，你确认后就能自动点歌\n"
                "· 搜索 歌名 / 点歌 序号 / 我的歌单 / 剩余次数 / 帮助"
            )
        await bot.call_api("send_private_msg", user_id=event.user_id, message=text)
    except Exception:
        logger.exception("发送新好友欢迎词失败")


@matcher.handle()
async def _(bot: Bot, event: MessageEvent):
    uid = event.get_user_id()
    text = event.get_plaintext().strip()

    # 管理命令：封禁 / 解封（仅超级管理员，先于封禁拦截处理）
    admin = parse_ban_command(text)
    if admin is not None:
        action, target = admin
        if not is_super_admin(uid):
            await matcher.finish("无权限：仅超级管理员可执行封禁/解封")
        if STORE.set_user_banned(target, action == "ban"):
            word = "封禁" if action == "ban" else "解封"
            await matcher.finish(f"已{word}用户 {target}")
        await matcher.finish(f"用户 {target} 不存在，无法解封")

    if is_ban_list_command(text):
        if not is_super_admin(uid):
            await matcher.finish("无权限：仅超级管理员可查看封禁列表")
        users = STORE.list_banned_users()
        if not users:
            await matcher.finish("当前没有被封禁的用户")
        await matcher.finish(
            "被封禁用户：" + "、".join(u["user_id"] for u in users)
        )

    if match_command(text, "封禁", "解封"):
        await matcher.finish(
            "用法：「封禁 用户ID」/「解封 用户ID」，仅超级管理员可用"
        )

    # 管理员：重置所有人今日点歌次数
    if is_reset_command(text):
        if not is_admin(uid):
            await matcher.finish("无权限：仅管理员可重置点歌次数")
        n = STORE.reset_all_daily_counts()
        await matcher.finish(f"已重置所有人的今日点歌次数（清零 {n} 条记录）")

    # 管理员：禁歌 / 解禁歌
    bs = parse_ban_song_command(text)
    if bs is not None:
        action, target = bs
        word = "禁播" if action == "ban" else "解禁"
        if not is_admin(uid):
            await matcher.finish(f"无权限：仅管理员可{word}歌曲")
        if target.isdigit():
            ok = STORE.set_song_banned(int(target), action == "ban")
            if ok:
                await matcher.finish(f"已{word}歌曲 #{target}")
            await matcher.finish(f"歌曲 #{target} 不存在，无法{word}")
        n = STORE.set_song_banned_by_name(target, action == "ban")
        await matcher.finish(f"已{word} {n} 首匹配《{target}》的歌曲")

    # 封禁拦截：点歌插件全部功能拒绝
    if STORE.is_user_banned(uid):
        await matcher.finish("你已被封禁，无法使用点歌功能")

    # 帮助选择：上一条是「帮助」，这一条当作编号处理
    if uid in _help_user:
        _help_user.discard(uid)
        key = text.strip().lstrip("/")

        # 3 / 4：不发说明，直接执行
        if key == "3":  # 我的歌单
            records = STORE.list_for_user(uid, RECORD_LIMIT)
            if not records:
                await matcher.finish(
                    "你还没有点歌记录。先「搜索 歌名」搜索，再「点歌 序号」即可点歌。"
                )
            img = await _render_records(records)
            if img is not None:
                await matcher.finish(MessageSegment.image(img))
            await matcher.finish(format_records(records))
        if key == "4":  # 剩余次数
            await matcher.finish(
                format_remaining(STORE.count_for_user_today(uid), DAILY_LIMIT)
            )

        detail = HELP_DETAILS.get(key)
        if detail is not None:
            if key == "1":  # 点歌：开启裸数字点歌模式
                _pending_mode[uid] = "song"
                await matcher.finish(
                    detail
                    + "\n\n已开启点歌模式：直接回复数字序号即可点歌；也可继续用「点歌 序号」。"
                )
            if key == "2":  # 搜索：开启裸文字搜索模式
                _pending_mode[uid] = "search"
                await matcher.finish(
                    detail
                    + "\n\n已开启搜索模式：直接发送歌名即可搜索；也可继续用「搜索 歌名」。"
                )
            await matcher.finish(detail + "\n\n该功能已开启，按上方说明使用。")

    # 已开启功能模式：处理下一条消息（一次性）
    if uid in _pending_mode:
        mode = _pending_mode.pop(uid)
        if mode == "song" and text.strip().isdigit():
            await _request_song(uid, int(text.strip()))
        elif mode == "search":
            kw = text.strip()
            cmds = (
                "帮助", "菜单", "我的歌单", "歌单", "点歌记录",
                "剩余次数", "查询剩余点歌次数", "剩余点歌次数",
                "上一页", "下一页", "退出搜索",
            )
            is_cmd = (kw in cmds) or kw.startswith(
                ("搜索", "点歌", "备注", "封禁", "解封", "帮助")
            )
            module = _find_search_plugin()
            if (not is_cmd) and kw and module is not None and hasattr(module, "do_search"):
                await matcher.finish(await module.do_search(uid, kw))

    # 帮助
    if match_command(text, "帮助", "菜单"):
        _help_user.add(uid)
        await matcher.finish(HELP_MENU)

    # 备注
    remark_parsed = parse_remark_command(text)
    if remark_parsed is not None:
        song_id, remark = remark_parsed
        if song_id is None:
            await matcher.finish(
                "用法：「备注 歌曲编号 内容」设置备注；「备注 歌曲编号」清除备注\n"
                "歌曲编号见「我的歌单」每条后面的 [编号N]"
            )
        if STORE.set_remark(uid, song_id, remark or ""):
            if remark:
                await matcher.finish(f"已为编号 {song_id} 的歌曲添加备注：{remark}")
            await matcher.finish(f"已清除编号 {song_id} 的歌曲备注")
        await matcher.finish(f"你没有点过编号为 {song_id} 的歌曲，无法备注")

    # 查看我的点歌记录（图片）
    if match_command(text, "查看我的点歌记录", "我的点歌记录", "点歌记录", "我的歌单", "歌单"):
        records = STORE.list_for_user(uid, RECORD_LIMIT)
        if not records:
            await matcher.finish(
                "你还没有点歌记录。先「搜索 歌名」搜索，再「点歌 序号」即可点歌。"
            )
        img = await _render_records(records)
        if img is not None:
            await matcher.finish(MessageSegment.image(img))
        await matcher.finish(format_records(records))

    # 查询剩余点歌次数
    if match_command(text, "查询剩余点歌次数", "剩余点歌次数", "剩余次数"):
        await matcher.finish(
            format_remaining(STORE.count_for_user_today(uid), DAILY_LIMIT)
        )

    # 点歌
    parsed = parse_request_command(text)
    if parsed is not None:
        index = parsed[0]
        if index is None:
            await matcher.finish(
                "用法：先「搜索 歌名」搜索歌曲，再「点歌 序号」点选结果，例如：点歌 3"
            )
        await _request_song(uid, index)

    # 其余消息不响应
    await matcher.finish()


async def _render_records(records: list[dict]) -> bytes | None:
    """把点歌记录渲染为 PNG（封面走搜索插件的缓存系统），失败返回 None。"""
    module = _find_search_plugin()
    if module is None:
        return None
    render_fn = getattr(module, "render_records", None)
    fetch_fn = getattr(module, "fetch_cached_cover", None)
    if render_fn is None or fetch_fn is None:
        return None
    tasks: dict[str, object] = {}
    for r in records:
        url = r.get("cover") or ""
        if not url or url in tasks:
            continue
        tasks[url] = fetch_fn(url, r.get("name") or "", r.get("artist") or "")
    covers: dict[str, object] = {}
    if tasks:
        covers = dict(zip(tasks.keys(), await asyncio.gather(*tasks.values())))
    try:
        return await asyncio.to_thread(render_fn, records, covers, len(records))
    except Exception:
        return None


async def _request_song(uid: str, index: int) -> None:
    search = get_last_search(uid)
    if not search or not search.get("songs"):
        await matcher.finish("你还没有搜索结果，先发送「搜索 歌名」搜索歌曲")

    songs = search["songs"]
    if index < 1 or index > len(songs):
        await matcher.finish(f"序号超出范围（1-{len(songs)}），请重新输入")

    info = songs[index - 1]
    name = str(info.get("name") or "未知歌曲")
    artist = str(info.get("artist") or "未知歌手")

    row = STORE.get_or_create_song(info)
    if row["is_banned"]:
        await matcher.finish(f"《{name} - {artist}》已被屏蔽，无法点播")

    if STORE.count_for_user_today(uid) >= DAILY_LIMIT:
        await matcher.finish(f"今日点歌次数已用完（{DAILY_LIMIT} 首），明天再来吧")

    STORE.ensure_user(uid)
    first = STORE.add_or_bump_request(uid, row["id"])
    used = STORE.count_for_user_today(uid)
    if first:
        await matcher.finish(f"点歌成功：{name} - {artist}\n今日已点 {used}/{DAILY_LIMIT} 首")
    await matcher.finish(
        f"《{name} - {artist}》已置顶你的歌单\n今日已点 {used}/{DAILY_LIMIT} 首"
    )
