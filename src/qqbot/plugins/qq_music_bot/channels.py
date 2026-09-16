"""消息通道抽象：把不同 adapter 的事件归一化为统一的收发接口。

- OneBot V11（NapCat）：私聊事件 + ``MessageSegment.image`` 发图
- 官方 QQ（nonebot-adapter-qq）：C2C 事件 + ``file_image`` 发图（adapter 自动走文件上传 API）

业务分发层只依赖 :class:`Channel`，不感知具体 adapter；
新增 adapter 只需在这里加一个工厂函数。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable


@dataclass
class Channel:
    adapter: str  # "onebot" / "qq"
    user_id: str
    send_text: Callable[[str], Awaitable[None]]
    send_image: Callable[[bytes], Awaitable[None]]


def from_onebot(bot, event) -> Channel:
    from nonebot.adapters.onebot.v11 import MessageSegment

    async def send_text(text: str) -> None:
        await bot.send(event, text)

    async def send_image(data: bytes) -> None:
        await bot.send(event, MessageSegment.image(data))

    return Channel(
        adapter="onebot",
        user_id=str(event.get_user_id()),
        send_text=send_text,
        send_image=send_image,
    )


def from_qq_c2c(bot, event) -> Channel:
    from nonebot.adapters.qq import MessageSegment

    async def send_text(text: str) -> None:
        await bot.send(event, MessageSegment.text(text))

    async def send_image(data: bytes) -> None:
        await bot.send(event, MessageSegment.file_image(data, "image.png"))

    return Channel(
        adapter="qq",
        user_id=str(event.get_user_id()),
        send_text=send_text,
        send_image=send_image,
    )
