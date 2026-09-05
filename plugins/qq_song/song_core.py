"""点歌解析与格式化。"""

from __future__ import annotations

import re

_SEP_RE = re.compile(r"[－-]")

HELP_MENU = (
    "点歌机器人指令说明：\n"
    "1. 点歌：开启点歌服务，之后按「歌名-歌手」发送歌曲\n"
    "2. 查看我的点歌记录：查看你点过的歌\n"
    "3. 查询剩余点歌次数：查询今天剩余可点次数\n"
    "提示：发送编号 1/2/3 可快速使用对应功能（仅打开本菜单后生效）；"
    "也可直接发送「点歌」「查看我的点歌记录」「查询剩余点歌次数」。"
)


def is_enable_command(text: str) -> bool:
    return (text or "").strip().lstrip("/").strip() == "点歌"


def match_command(text: str, *keywords: str) -> bool:
    t = re.sub(r"\s+", "", text or "")
    return any(kw in t for kw in keywords if kw)


def parse_song_payload(payload: str) -> tuple[str, str] | None:
    payload = (payload or "").strip().strip(" \t，,。:：；;")
    if not _SEP_RE.search(payload):
        return None
    parts = [p.strip() for p in _SEP_RE.split(payload)]
    if len(parts) != 2:
        return None
    name, artist = parts
    if not name or not artist:
        return None
    return name, artist


def format_records(records: list[dict]) -> str:
    if not records:
        return "你还没有点歌记录。使用「点歌」开启服务后，发送「歌名-歌手」即可点歌。"
    lines = [f"你的点歌记录（共 {len(records)} 条，最近在前）："]
    for i, r in enumerate(records, 1):
        time_s = (r.get("time") or "")[:16].replace("T", " ")
        lines.append(f"{i}. {r['song']} - {r['artist']}（{time_s}）")
    return "\n".join(lines)


def format_remaining(used: int, limit: int) -> str:
    return f"今天已点 {used}/{limit} 首，剩余可点 {max(0, limit - used)} 首。"
