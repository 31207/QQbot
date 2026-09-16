"""日期/字符串工具。"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

BEIJING_TZ = ZoneInfo("Asia/Shanghai")

_WEEK_CN = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]


def beijing_now() -> datetime:
    """北京时间（带时区）。"""
    return datetime.now(BEIJING_TZ)


def beijing_naive_now() -> datetime:
    """北京时间的裸 datetime（与库中无时区时间戳对齐用）。"""
    return datetime.now(BEIJING_TZ).replace(tzinfo=None)


def load_dotenv(path: Path) -> dict[str, str]:
    """解析 dotenv 文件（支持 KEY=VALUE / 注释 / 空行），返回键值字典。"""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key:
            values[key] = value.strip().strip('"').strip("'")
    return values


def today_key(now: datetime | None = None) -> str:
    return (now or datetime.now()).strftime("%Y-%m-%d")


def week_key(now: datetime | None = None) -> str:
    """当前自然周（周一起）的起始日期字符串。"""
    now = now or datetime.now()
    return (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")


def compact(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def format_date_cn(value) -> str:
    """把 ISO 字符串或 datetime 格式化成「M月D日 星期X」；失败返回原值。"""
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value)
        except ValueError:
            return value
    elif isinstance(value, datetime):
        dt = value
    else:
        return str(value)
    return f"{dt.month}月{dt.day}日 {_WEEK_CN[dt.weekday()]}"


def format_short_time(value) -> str:
    """datetime 或 ISO 字符串 → 「MM-DD HH:MM」。"""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return (value or "")[:16].replace("T", " ")
    return f"{value:%m-%d %H:%M}"
