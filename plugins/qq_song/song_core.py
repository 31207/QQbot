"""点歌指令解析与格式化。"""

from __future__ import annotations

import re

_POINT_RE = re.compile(r"^点歌(?:\s*(\d+))?$")
_REMARK_RE = re.compile(r"^备注(?:\s*(\d+)(?:\s+([\s\S]*))?)?$")
_BAN_RE = re.compile(r"^封禁\s*(\d+)$")
_UNBAN_RE = re.compile(r"^解封\s*(\d+)$")

HELP_MENU = (
    "点歌机器人指令说明（仅私聊）：\n"
    "1. 搜索 歌名：搜索歌曲（可加平台前缀，如「搜索 qq 晴天」）\n"
    "2. 点歌 序号：点选最近一次搜索结果（如「点歌 3」；重复点歌会置顶歌单，当日次数照扣）\n"
    "3. 我的歌单/点歌记录：查看你点过的歌\n"
    "4. 查询剩余点歌次数：查询今天剩余可点次数\n"
    "5. 备注 歌曲编号 内容：给已点歌曲加备注（「备注 编号」清除备注）\n"
    "管理命令（仅超级管理员）：封禁 用户ID / 解封 用户ID / 封禁列表"
)


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
