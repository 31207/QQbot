"""权限白名单（三级：用户 / 管理员 / 超级管理员）。

权限只能从 data/permissions.json 白名单文件授予；按文件修改时间自动热加载，
机器人端无法授予权限。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger("qqbot.permissions")


class Permissions:
    def __init__(
        self,
        path: Path,
        week_limit: int = 5,
        admin_daily_limit: int = 99,
    ) -> None:
        self._path = path
        self._week_limit = week_limit
        self._admin_daily_limit = admin_daily_limit
        self._data: dict[str, list[str]] = {"admins": [], "super_admins": []}
        self._mtime: float = -1.0
        self._load()

    def _load(self) -> None:
        try:
            mtime = self._path.stat().st_mtime if self._path.exists() else -1.0
            if mtime == self._mtime:
                return
            raw = json.loads(self._path.read_text(encoding="utf-8")) if self._path.exists() else {}
            self._data = {
                "admins": [str(x) for x in raw.get("admins", [])],
                "super_admins": [str(x) for x in raw.get("super_admins", [])],
            }
            self._mtime = mtime
        except Exception:
            logger.exception("读取权限白名单失败")
            self._data = {"admins": [], "super_admins": []}
            self._mtime = -1.0

    def is_admin(self, user_id: str) -> bool:
        self._load()
        return user_id in self._data["admins"] or user_id in self._data["super_admins"]

    def is_super_admin(self, user_id: str) -> bool:
        self._load()
        return user_id in self._data["super_admins"]

    def role_limit(self, user_id: str) -> tuple[str, int]:
        """返回 (周期文案, 上限)。管理员及以上按日、普通用户按周。"""
        if self.is_admin(user_id):
            return ("今天", self._admin_daily_limit)
        return ("本周", self._week_limit)
