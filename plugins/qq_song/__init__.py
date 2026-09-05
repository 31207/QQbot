"""点歌插件（NoneBot2 / OneBot v11，仅私聊）。

流程：「搜索 歌名」得到结果图 →「点歌 序号」选取歌曲：
- 按 (source, id) 查找歌曲库，不存在则入库（is_banned=0、play_count=0）
- 已 ban → 报错；超每日上限 → 报错
- 用户不存在则创建；重复点歌则记录置顶且当日次数照扣
- 「我的歌单」等以图片展示点歌记录（含封面/编号/备注）
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from nonebot import get_driver, get_loaded_plugins, on_message
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, MessageSegment
from nonebot.rule import Rule, to_me

from .song_core import (
    HELP_MENU,
    format_records,
    format_remaining,
    is_ban_list_command,
    match_command,
    parse_ban_command,
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

def _find_search_plugin():
    for plugin in get_loaded_plugins():
        if plugin.name == "qq_music_search" and plugin.module:
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


@matcher.handle()
async def _(bot: Bot, event: MessageEvent):
    uid = event.get_user_id()
    text = event.get_plaintext().strip()

    # 管理命令：封禁 / 解封（仅超级管理员，先于封禁拦截处理）
    admin = parse_ban_command(text)
    if admin is not None:
        action, target = admin
        if uid not in SUPERUSERS:
            await matcher.finish("无权限：仅超级管理员可执行封禁/解封")
        if STORE.set_user_banned(target, action == "ban"):
            word = "封禁" if action == "ban" else "解封"
            await matcher.finish(f"已{word}用户 {target}")
        await matcher.finish(f"用户 {target} 不存在，无法解封")

    if is_ban_list_command(text):
        if uid not in SUPERUSERS:
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

    # 封禁拦截：点歌插件全部功能拒绝
    if STORE.is_user_banned(uid):
        await matcher.finish("你已被封禁，无法使用点歌功能")

    # 帮助
    if match_command(text, "帮助", "菜单"):
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
