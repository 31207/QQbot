"""点歌插件（NoneBot2 / OneBot v11）。"""

import os
from pathlib import Path

from nonebot import on_message
from nonebot.adapters.onebot.v11 import Bot, MessageEvent
from nonebot.rule import to_me

from .song_core import (
    HELP_MENU,
    format_records,
    format_remaining,
    is_enable_command,
    match_command,
    parse_song_payload,
)
from .storage import SongRequestStore

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # 项目根目录
_data_file = os.environ.get("QQ_SONG_DATA_FILE") or str(
    _PROJECT_ROOT / "data" / "song_requests.db"
)
STORE = SongRequestStore(_data_file)
DAILY_LIMIT = int(os.environ.get("QQ_SONG_DAILY_LIMIT", "5") or "5")
RECORD_LIMIT = int(os.environ.get("QQ_SONG_RECORD_LIMIT", "20") or "20")

# 每个用户的状态：{"song": 点歌模式, "help": 帮助已打开}
_state: dict[str, dict] = {}

matcher = on_message(priority=5, block=True, rule=to_me())


@matcher.handle()
async def _(bot: Bot, event: MessageEvent):
    uid = event.get_user_id()
    text = event.get_plaintext().strip()
    st = _state.setdefault(uid, {})
    scene = "c2c" if event.message_type == "private" else "channel"

    # 帮助
    if match_command(text, "帮助", "菜单"):
        st["help"] = True
        await matcher.finish(HELP_MENU)

    # 快捷键（仅帮助打开后的下一条消息有效）
    if st.get("help"):
        st["help"] = False
        if text == "1":
            st["song"] = True
            await matcher.finish("点歌服务已开启")
        if text == "2":
            await matcher.finish(format_records(STORE.list_for_user(uid, RECORD_LIMIT)))
        if text == "3":
            await matcher.finish(
                format_remaining(STORE.count_for_user_today(uid), DAILY_LIMIT)
            )

    # 查看我的点歌记录
    if match_command(text, "查看我的点歌记录", "我的点歌记录", "点歌记录"):
        await matcher.finish(format_records(STORE.list_for_user(uid, RECORD_LIMIT)))

    # 查询剩余点歌次数
    if match_command(text, "查询剩余点歌次数", "剩余点歌次数", "剩余次数"):
        await matcher.finish(
            format_remaining(STORE.count_for_user_today(uid), DAILY_LIMIT)
        )

    # 开启点歌
    if is_enable_command(text):
        st["song"] = True
        await matcher.finish("点歌服务已开启")

    # 点歌模式：解析“歌名-歌手”
    if st.get("song"):
        parsed = parse_song_payload(text)
        if parsed:
            name, artist = parsed
            STORE.append(
                scene=scene,
                user_id=uid,
                song=name,
                artist=artist,
                raw=text,
                msg_id=event.message_id,
            )
            await matcher.finish("信息已录入")
        await matcher.finish("输入信息有误")

    await matcher.finish(
        "先发送「点歌」开启点歌服务，再按「歌名-歌手」格式发送歌曲；"
        "例如：先发「点歌」，再发「晴天-周杰伦」"
    )
