import os

import nonebot

from qqbot import config


def _stub_nonebot(monkeypatch):
    """让 _env 跳过 NoneBot 分支（conftest 已初始化 nonebot，会读到真实 .env.prod）。"""
    monkeypatch.setattr(
        nonebot, "get_driver", lambda: (_ for _ in ()).throw(RuntimeError("stub"))
    )


def test_env_os_environ_priority(monkeypatch):
    _stub_nonebot(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", "shell-value")
    assert config._env("DATABASE_URL") == "shell-value"


def test_env_default(monkeypatch):
    _stub_nonebot(monkeypatch)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert config._env("DATABASE_URL", "default") == "default"
