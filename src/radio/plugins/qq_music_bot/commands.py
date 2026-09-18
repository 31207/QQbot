"""指令解析（纯函数，无副作用，可直接单测）。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from radio.util import compact

_POINT_RE = re.compile(r"^点歌(?:\s*(\d+))?$")
_REMARK_RE = re.compile(r"^备注(?:\s*(\d+)(?:\s+([\s\S]*))?)?$")
_BAN_RE = re.compile(r"^封禁\s*(\d+)$")
_UNBAN_RE = re.compile(r"^解封\s*(\d+)$")
_BAN_SONG_RE = re.compile(r"^(?:禁歌|禁唱)\s*(.+)$")
_UNBAN_SONG_RE = re.compile(r"^(?:解禁歌|解禁唱|允许歌)\s*(.+)$")

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


class CommandKind(str, Enum):
    SEARCH = "search"
    SEARCH_NEXT = "search_next"
    SEARCH_PREV = "search_prev"
    SEARCH_EXIT = "search_exit"
    ORDER = "order"
    MY_SONGS = "my_songs"
    REMAINING = "remaining"
    MY_ID = "my_id"
    REMARK = "remark"
    HELP = "help"
    BAN_USER = "ban_user"
    UNBAN_USER = "unban_user"
    BAN_LIST = "ban_list"
    BAN_SONG = "ban_song"
    UNBAN_SONG = "unban_song"
    RESET_QUOTA = "reset_quota"
    NOTICE_STATUS = "notice_status"
    NOTICE_SEND = "notice_send"


@dataclass(frozen=True)
class Command:
    kind: CommandKind
    args: tuple = ()


ADMIN_KINDS = frozenset(
    {
        CommandKind.BAN_USER,
        CommandKind.UNBAN_USER,
        CommandKind.BAN_LIST,
        CommandKind.BAN_SONG,
        CommandKind.UNBAN_SONG,
        CommandKind.RESET_QUOTA,
        CommandKind.NOTICE_STATUS,
        CommandKind.NOTICE_SEND,
    }
)


def parse_command(text: str) -> Command | None:
    """解析用户消息为 Command；非指令返回 None。"""
    t = (text or "").lstrip("/").strip()
    if not t:
        return None
    c = compact(t)

    if c == "上一页":
        return Command(CommandKind.SEARCH_PREV)
    if c == "下一页":
        return Command(CommandKind.SEARCH_NEXT)
    if c == "退出搜索":
        return Command(CommandKind.SEARCH_EXIT)

    if t.startswith("搜索"):
        rest = t[2:].strip()
        parts = rest.split(maxsplit=1)
        if parts and parts[0].lower() in _ALIAS_TO_SOURCE:
            source = _ALIAS_TO_SOURCE[parts[0].lower()]
            keyword = parts[1].strip() if len(parts) > 1 else ""
            return Command(CommandKind.SEARCH, (source, keyword))
        return Command(CommandKind.SEARCH, (None, rest))

    m = _POINT_RE.match(t)
    if m:
        return Command(CommandKind.ORDER, (int(m.group(1)) if m.group(1) else None,))

    m = _REMARK_RE.match(t)
    if m:
        if m.group(1) is None:
            return Command(CommandKind.REMARK, (None, None))
        return Command(CommandKind.REMARK, (int(m.group(1)), (m.group(2) or "").strip()))

    m = _BAN_RE.match(t)
    if m:
        return Command(CommandKind.BAN_USER, (m.group(1),))
    m = _UNBAN_RE.match(t)
    if m:
        return Command(CommandKind.UNBAN_USER, (m.group(1),))

    if c in ("封禁列表", "解封列表"):
        return Command(CommandKind.BAN_LIST)

    m = _BAN_SONG_RE.match(t)
    if m:
        return Command(CommandKind.BAN_SONG, (m.group(1).strip(),))
    m = _UNBAN_SONG_RE.match(t)
    if m:
        return Command(CommandKind.UNBAN_SONG, (m.group(1).strip(),))

    if c in ("重置点歌次数", "重置", "清空点歌次数"):
        return Command(CommandKind.RESET_QUOTA)

    if c in ("通知状态", "通知情况", "通知列表"):
        return Command(CommandKind.NOTICE_STATUS)
    if c in ("发送通知", "通知发送", "立即发送通知"):
        return Command(CommandKind.NOTICE_SEND)

    if c in ("我的歌单", "点歌记录", "歌单", "查看我的点歌记录", "我的点歌记录"):
        return Command(CommandKind.MY_SONGS)

    if c in ("剩余次数", "查询剩余点歌次数", "剩余点歌次数"):
        return Command(CommandKind.REMAINING)

    if c.lower() in ("id", "我的id", "用户id", "我的用户id", "查询id"):
        return Command(CommandKind.MY_ID)

    if c.startswith("帮助") or c.startswith("菜单"):
        return Command(CommandKind.HELP)

    return None
