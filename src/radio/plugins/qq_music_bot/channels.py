"""消息通道抽象：把不同 adapter 的事件归一化为统一的收发接口。

- OneBot V11（NapCat）：私聊事件 + ``MessageSegment.image`` 发图
- 官方 QQ（nonebot-adapter-qq）：
  - C2C 单聊：``C2CMessageCreateEvent``，``file_image`` 发图（自动走文件上传 API）
  - 频道私信：``DirectMessageCreateEvent``，``file_image`` 发图（自动走 DMS 文件上传）

业务用户 ID 带平台前缀，业务层无需感知 adapter，发送时按前缀路由：

- ``onebot:<QQ号>``
- ``c2c:<user_openid>``
- ``dms:<guild_id>:<频道用户id>``

新增 adapter 只需在这里加一个工厂函数。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

ONEBOT_PREFIX = "onebot"
C2C_PREFIX = "c2c"
DMS_PREFIX = "dms"


def encode_uid(platform: str, *parts: str) -> str:
    """编码业务用户 ID：``onebot:123`` / ``c2c:xxx`` / ``dms:guild:user``。"""
    return ":".join([platform, *[str(part) for part in parts]])


def split_uid(uid: str) -> tuple[str, list[str]]:
    """解析业务用户 ID 为 ``(平台, 标识段)``；无前缀时平台为 ``""``。"""
    parts = str(uid or "").split(":")
    if len(parts) < 2 or not parts[1]:
        return "", [str(uid or "")]
    return parts[0], parts[1:]


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
        user_id=encode_uid(ONEBOT_PREFIX, event.get_user_id()),
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
        user_id=encode_uid(C2C_PREFIX, event.get_user_id()),
        send_text=send_text,
        send_image=send_image,
    )


def from_qq_dms(bot, event) -> Channel:
    """QQ 频道私信（direct message）。"""
    from nonebot.adapters.qq import MessageSegment

    async def send_text(text: str) -> None:
        await bot.send(event, MessageSegment.text(text))

    async def send_image(data: bytes) -> None:
        await bot.send(event, MessageSegment.file_image(data, "image.png"))

    return Channel(
        adapter="qq",
        user_id=encode_uid(DMS_PREFIX, event.guild_id, event.get_user_id()),
        send_text=send_text,
        send_image=send_image,
    )
