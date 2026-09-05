"""点歌指令解析与格式化。"""

from __future__ import annotations

import re

_POINT_RE = re.compile(r"^点歌(?:\s*(\d+))?$")
_REMARK_RE = re.compile(r"^备注(?:\s*(\d+)(?:\s+([\s\S]*))?)?$")
_BAN_RE = re.compile(r"^封禁\s*(\d+)$")
_UNBAN_RE = re.compile(r"^解封\s*(\d+)$")

HELP_MENU = (
    "点歌机器人功能菜单，回复编号：\n"
    "1. 点歌\n"
    "2. 搜索歌曲\n"
    "3. 我的歌单\n"
    "4. 查询剩余点歌次数\n"
    "5. 备注"
)

HELP_DETAILS = {
    "1": (
        "【点歌】\n"
        "先「搜索 歌名」得到结果，再「点歌 序号」点选；开启后可直接发数字序号选歌\n"
        "例：搜索 晴天 → 点歌 3\n"
        "每日有上限；重复点歌会置顶歌单，当日次数照扣"
    ),
    "2": (
        "【搜索歌曲】\n"
        "「搜索 歌名」全平台搜索；「搜索 平台 歌名」指定平台\n"
        "例：搜索 晴天 / 搜索 qq 晴天\n"
        "支持：网易云、QQ音乐、酷狗、酷我、咪咕、汽水、千千、JOOX、Jamendo、B站\n"
        "开启后直接发送歌名即可搜索；搜索后用「上一页 / 下一页 / 退出搜索」翻页"
    ),
    "5": (
        "【备注】\n"
        "「备注 歌曲编号 内容」为已点歌曲加备注；「备注 歌曲编号」清除备注\n"
        "歌曲编号见「我的歌单」每条后面的 [编号N]"
    ),
}


def match_command(text: str, *keywords: str) -> bool:
    t = re.sub(r"\s+", "", text or "")
    return any(kw in t for kw in keywords if kw)


def parse_request_command(text: str) -> tuple[int | None] | None:
    """「点歌 [序号]」→ (序号,)，仅「点歌」→ (None,)，非点歌指令 → None。"""
    t = (text or "").lstrip("/").strip()
    m = _POINT_RE.match(t)
    if not m:
        return None
    return (int(m.group(1)) if m.group(1) else None,)


def parse_remark_command(text: str) -> tuple[int | None, str | None] | None:
    """「备注 编号 [内容]」→ (编号, 内容)；仅「备注」→ (None, None)；非备注指令 → None。"""
    t = (text or "").lstrip("/").strip()
    if not t.startswith("备注"):
        return None
    m = _REMARK_RE.match(t)
    if not m or m.group(1) is None:
        return (None, None)
    return (int(m.group(1)), (m.group(2) or "").strip())


def parse_ban_command(text: str) -> tuple[str, str] | None:
    """「封禁 用户ID」→ ("ban", id)；「解封 用户ID」→ ("unban", id)；其他 → None。"""
    t = (text or "").lstrip("/").strip()
    m = _BAN_RE.match(t)
    if m:
        return ("ban", m.group(1))
    m = _UNBAN_RE.match(t)
    if m:
        return ("unban", m.group(1))
    return None


def is_ban_list_command(text: str) -> bool:
    t = (text or "").lstrip("/").strip()
    return re.sub(r"\s+", "", t) in ("封禁列表", "解封列表")


def format_records(records: list[dict]) -> str:
    if not records:
        return "你还没有点歌记录。先「搜索 歌名」搜索，再「点歌 序号」即可点歌。"
    lines = [f"你的点歌记录（共 {len(records)} 条，最近在前）："]
    for i, r in enumerate(records, 1):
        time_s = (r.get("time") or "")[:16].replace("T", " ")
        remark = (r.get("remark") or "").strip()
        line = f"{i}. {r['name']} - {r['artist']} [编号{r['song_id']}]（{time_s}）"
        if remark:
            line += f"\n   备注：{remark}"
        lines.append(line)
    return "\n".join(lines)


def format_remaining(used: int, limit: int) -> str:
    return f"今天已点 {used}/{limit} 首，剩余可点 {max(0, limit - used)} 首。"
