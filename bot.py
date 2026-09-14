"""NoneBot2 入口。

依赖安装：``pip install -e .``（editable，保证 import qqbot 可用）。
"""

import nonebot
from nonebot.adapters.onebot.v11 import Adapter

nonebot.init()
nonebot.get_driver().register_adapter(Adapter)
nonebot.load_from_toml("pyproject.toml")

if __name__ == "__main__":
    nonebot.run()
