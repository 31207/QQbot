"""NoneBot2 入口（双 adapter：OneBot V11 + 官方 QQ）。

依赖安装：``pip install -e .``（editable，保证 import radio 可用）。
官方 QQ 需要在 .env 配置 QQ_BOTS（JSON 数组：id/token/secret），
不配也可以只跑 OneBot（NapCat）。
"""

import nonebot
from nonebot.adapters.onebot.v11 import Adapter
from nonebot.adapters.qq import Adapter as QQAdapter

nonebot.init()
driver = nonebot.get_driver()
driver.register_adapter(Adapter)
driver.register_adapter(QQAdapter)
nonebot.load_builtin_plugins('echo', 'single_session')
nonebot.load_from_toml("pyproject.toml")

if __name__ == "__main__":
    nonebot.run()
