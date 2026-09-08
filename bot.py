"""NoneBot2 入口。"""

import os

import nonebot
from nonebot.adapters.onebot.v11 import Adapter

nonebot.init()

# 允许通过 .env 配置 DATABASE_URL 切换数据库（系统环境变量优先级更高）。
# NoneBot 不会把 .env 的键自动注入 os.environ，这里补一步，让 bot 的 db 层读到。
if not os.environ.get("DATABASE_URL"):
    _db_url = getattr(nonebot.get_driver().config, "database_url", None)
    if _db_url:
        os.environ["DATABASE_URL"] = str(_db_url)

nonebot.get_driver().register_adapter(Adapter)
nonebot.load_from_toml("pyproject.toml")


if __name__ == "__main__":
    nonebot.run()
