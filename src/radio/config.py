"""统一配置。

- bot 进程：从 NoneBot 配置读取（nonebot.init() 已合并环境变量与 .env / .env.prod）；
- web-admin 进程：由 backend 启动时自行读取 `web-admin/backend/.env`
  注入环境变量（见 web-admin/backend/app.py），本模块只认环境变量；
- 读取优先级：系统环境变量 → NoneBot 配置 → 默认值。

所有配置项只在 radio.config 里解析一次，其它模块直接 ``from radio.config import settings``。
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _env(name: str, default: str = "") -> str:
    """环境变量 → NoneBot 配置 → 默认值。"""
    value = os.environ.get(name)
    if not value or not value.strip():
        try:
            from nonebot import get_driver

            value = getattr(get_driver().config, name.lower(), None)
            if value is not None:
                value = str(value)
        except Exception:
            value = None
    if not value or not value.strip():
        return default
    return value.strip()


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name) or default)
    except ValueError:
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    value = _env(name)
    if not value:
        return default
    return value.lower() in ("1", "true", "yes", "on")


class Settings:
    """进程级配置快照。"""

    def __init__(self) -> None:
        self.database_url: str = _env("DATABASE_URL")
        self.music_api_base: str = _env("QQ_MUSIC_API_BASE", "http://127.0.0.1:8081").rstrip("/")
        self.cover_dir: Path = Path(
            _env("QQ_MUSIC_COVER_DIR") or str(PROJECT_ROOT / "data" / "covers")
        )
        self.page_size: int = _env_int("QQ_MUSIC_PAGE_SIZE", 10)
        self.session_ttl: int = _env_int("QQ_MUSIC_SESSION_TTL", 600)

        self.week_limit: int = _env_int("QQ_SONG_WEEK_LIMIT", 5)
        self.admin_daily_limit: int = _env_int("QQ_SONG_ADMIN_DAILY_LIMIT", 99)
        self.record_limit: int = _env_int("QQ_SONG_RECORD_LIMIT", 20)

        self.permissions_file: Path = Path(
            _env("QQ_PERMISSIONS_FILE") or str(PROJECT_ROOT / "data" / "permissions.json")
        )

        self.llm_enabled: bool = _env_bool("LLM_ENABLED")
        self.llm_api_base: str = _env("LLM_API_BASE").rstrip("/")
        self.llm_api_key: str = _env("LLM_API_KEY")
        self.llm_model: str = _env("LLM_MODEL", "deepseek-chat")
        self.llm_timeout: float = float(_env("LLM_TIMEOUT", "30") or 30)
        self.llm_memory_ttl: int = _env_int("LLM_MEMORY_TTL", 1800)
        self.llm_memory_turns: int = _env_int("LLM_MEMORY_TURNS", 12)
        self.llm_max_steps: int = _env_int("LLM_MAX_STEPS", 4)

        self.web_admin_username: str = _env("WEB_ADMIN_USERNAME", "admin")
        self.web_admin_password: str = _env("WEB_ADMIN_PASSWORD")
        self.web_admin_token: str = _env("WEB_ADMIN_TOKEN")
        self.web_admin_port: int = _env_int("WEB_ADMIN_PORT", 8600)
        self.web_cors_origins: list[str] = [
            o.strip() for o in _env("WEB_ADMIN_CORS", "*").split(",") if o.strip()
        ]


settings = Settings()