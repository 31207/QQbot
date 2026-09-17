"""向数据库注入演示数据：模拟点歌流程（100 首各种类型歌曲 + 用户点歌 + 备注 + 部分选用/禁播/通知）。

用法（QQbot 项目根目录）：
    .venv/bin/python scripts/seed_demo.py [--clear]

- 数据库连接串：环境变量 DATABASE_URL 或项目 .env / .env.prod（自动读取）；
- --clear：先清空全部业务表再注入；
- 随机种子固定，可重复执行（歌曲经 get_or_create 幂等，点歌记录会叠加）。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import random
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, select

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 先注入 .env / .env.prod 的配置（与 bot 进程一致），再导入 qqbot
from qqbot.util import load_dotenv  # noqa: E402

for _key, _value in load_dotenv(_PROJECT_ROOT / ".env").items():
    os.environ.setdefault(_key, _value)
for _key, _value in load_dotenv(_PROJECT_ROOT / ".env.prod").items():
    os.environ.setdefault(_key, _value)

from qqbot.db import get_session_factory, init_db  # noqa: E402
from qqbot.db.models import PlayHistory, Song, SongSelectedNotice, User, UserRequest  # noqa: E402
from qqbot.services.notices import NoticeService  # noqa: E402
from qqbot.services.permissions import Permissions  # noqa: E402
from qqbot.services.requests import RequestService  # noqa: E402
from qqbot.services.songs import SongService  # noqa: E402
from qqbot.services.users import UserService  # noqa: E402
from qqbot.util import today_key, week_key  # noqa: E402

# (source, 歌名, 歌手) —— 覆盖纯音乐/重金属/电音喊麦/广告曲/流行/民谣/摇滚等类型
SONG_POOL: list[tuple[str, str, str]] = [
    ("netease", "夜的钢琴曲五", "石进"),
    ("netease", "天空之城", "久石让"),
    ("netease", "Summer", "久石让"),
    ("netease", "菊次郎的夏天", "久石让"),
    ("kugou", "卡农钢琴版", "Canon in D"),
    ("kugou", "梦中的婚礼", "理查德·克莱德曼"),
    ("kugou", "雨的印记", "Yiruma"),
    ("migu", "River Flows in You", "Yiruma"),
    ("migu", "克罗地亚狂想曲", "Maksim"),
    ("migu", "出埃及记", "Maksim"),
    ("kuwo", "野蜂飞舞", "马克西姆"),
    ("kuwo", "蓝色多瑙河", "小约翰·施特劳斯"),
    ("qq", "Master of Puppets", "Metallica"),
    ("qq", "Enter Sandman", "Metallica"),
    ("qq", "Raining Blood", "Slayer"),
    ("netease", "Angel of Death", "Slayer"),
    ("netease", "Painkiller", "Judas Priest"),
    ("netease", "Ace of Spades", "Motörhead"),
    ("kugou", "Paranoid", "Black Sabbath"),
    ("kugou", "War Pigs", "Black Sabbath"),
    ("kuwo", "Holy Diver", "Dio"),
    ("kuwo", "Symphony of Destruction", "Megadeth"),
    ("qq", "Faded", "Alan Walker"),
    ("qq", "Alone", "Alan Walker"),
    ("qq", "Wake Me Up", "Avicii"),
    ("netease", "Levels", "Avicii"),
    ("netease", "Animals", "Martin Garrix"),
    ("kugou", "Closer", "The Chainsmokers"),
    ("kugou", "Don't Let Me Down", "The Chainsmokers"),
    ("kuwo", "Titanium", "David Guetta"),
    ("migu", "惊雷", "MC梦柯"),
    ("migu", "一人饮酒醉", "MC天佑"),
    ("bilibili", "野狼disco", "宝石Gem"),
    ("bilibili", "蜜雪冰城甜蜜蜜", "蜜雪冰城"),
    ("bilibili", "拼多多推广神曲", "网络热曲"),
    ("qianqian", "直播间热卖BGM", "DJ版"),
    ("qianqian", "洗脑广告曲·团购版", "网络热曲"),
    ("qq", "晴天", "周杰伦"),
    ("qq", "七里香", "周杰伦"),
    ("qq", "稻香", "周杰伦"),
    ("qq", "青花瓷", "周杰伦"),
    ("qq", "告白气球", "周杰伦"),
    ("qq", "简单爱", "周杰伦"),
    ("qq", "以父之名", "周杰伦"),
    ("qq", "龙卷风", "周杰伦"),
    ("qq", "千里之外", "周杰伦"),
    ("qq", "菊花台", "周杰伦"),
    ("qq", "说好不哭", "周杰伦/阿信"),
    ("qq", "凉凉", "杨宗纬/张碧晨"),
    ("netease", "孤勇者", "陈奕迅"),
    ("netease", "十年", "陈奕迅"),
    ("netease", "浮夸", "陈奕迅"),
    ("netease", "富士山下", "陈奕迅"),
    ("netease", "光年之外", "邓紫棋"),
    ("netease", "泡沫", "邓紫棋"),
    ("netease", "无问", "毛不易"),
    ("kugou", "平凡之路", "朴树"),
    ("kugou", "生如夏花", "朴树"),
    ("kugou", "那些花儿", "朴树"),
    ("kugou", "成都", "赵雷"),
    ("kugou", "南方姑娘", "赵雷"),
    ("kugou", "鼓楼", "赵雷"),
    ("kuwo", "消愁", "毛不易"),
    ("kuwo", "像我这样的人", "毛不易"),
    ("kuwo", "起风了", "买辣椒也用券"),
    ("kuwo", "岁月神偷", "金玟岐"),
    ("kuwo", "芒种", "音阙诗听"),
    ("migu", "光", "陈粒"),
    ("migu", "小半", "陈粒"),
    ("migu", "易燃易爆炸", "陈粒"),
    ("migu", "追光者", "岑宁儿"),
    ("migu", "小幸运", "田馥甄"),
    ("migu", "魔鬼中的天使", "田馥甄"),
    ("migu", "纸短情长", "烟把儿"),
    ("soda", "海阔天空", "Beyond"),
    ("soda", "光辉岁月", "Beyond"),
    ("soda", "真的爱你", "Beyond"),
    ("soda", "红日", "李克勤"),
    ("soda", "月半小夜曲", "李克勤"),
    ("soda", "江南", "林俊杰"),
    ("soda", "修炼爱情", "林俊杰"),
    ("soda", "一千年以后", "林俊杰"),
    ("soda", "可惜没如果", "林俊杰"),
    ("soda", "光年之外的你", "网络热曲"),
    ("qianqian", "后来", "刘若英"),
    ("qianqian", "勇气", "梁静茹"),
    ("qianqian", "暖暖", "梁静茹"),
    ("qianqian", "演员", "薛之谦"),
    ("qianqian", "绅士", "薛之谦"),
    ("qianqian", "丑八怪", "薛之谦"),
    ("bilibili", "夜空中最亮的星", "逃跑计划"),
    ("bilibili", "一万次悲伤", "逃跑计划"),
    ("bilibili", "追梦赤子心", "GALA"),
    ("bilibili", "理想三旬", "陈鸿宇"),
    ("bilibili", "春风十里", "鹿先森乐队"),
    ("joox", "昨日青空", "尤长靖"),
    ("joox", "飞云之下", "林俊杰/韩红"),
    ("jamendo", "董小姐", "宋冬野"),
    ("jamendo", "安河桥", "宋冬野"),
    ("jamendo", "理想", "赵雷"),
]

USERS = [f"1{i:05d}" for i in range(1, 31)]  # 30 个模拟 QQ 号
REMARKS = ["", "", "", "", "生日祝福", "毕业季", "点给同桌", "高考加油", "运动会加油"]

SELECTED_COUNT = 8
BANNED_SOURCE_IDS = {"seed11", "seed15", "seed21", "seed31", "seed35", "seed36"}  # 纯音乐/重金属/喊麦等样例


def _song_info(i: int, item: tuple[str, str, str]) -> dict:
    source, name, artist = item
    has_link = i % 3 != 0  # 约 2/3 的歌曲带链接（供抽取结果展示）
    return {
        "source": source,
        "id": f"seed{i}",
        "name": name,
        "artist": artist,
        "album": "",
        "cover": "",
        "duration": 150 + (i * 37) % 180,
        "url": f"https://audio.example.com/seed{i}.mp3" if has_link else "",
        "link": f"https://music.example.com/seed{i}" if has_link else "",
    }


async def _clear() -> None:
    factory = get_session_factory()
    async with factory() as s:
        for table in (SongSelectedNotice, PlayHistory, UserRequest, User, Song):
            await s.execute(delete(table))
        await s.commit()
    print("已清空业务表")


async def _seed_users() -> None:
    rng = random.Random(1)
    factory = get_session_factory()
    async with factory() as s:
        for uid in USERS:
            created = datetime.now() - timedelta(days=rng.randint(5, 40))
            s.add(User(user_id=uid, is_banned=False, created_at=created))
        await s.commit()
    print(f"已创建 {len(USERS)} 个用户")


async def _seed_songs() -> dict[int, dict]:
    songs = SongService()
    info_by_id: dict[int, dict] = {}
    for i, item in enumerate(SONG_POOL):
        row = await songs.get_or_create(_song_info(i, item))  # 走真实点歌流程的歌曲入库路径
        info_by_id[row["id"]] = _song_info(i, item)
    print(f"歌曲库 {len(SONG_POOL)} 首（get_or_create 幂等）")
    return info_by_id


async def _seed_requests(info_by_id: dict[int, dict]) -> None:
    """历史 6 天直接写记录（按 day/week 计数），今天走真实 order 流程。"""
    rng = random.Random(42)
    factory = get_session_factory()
    # 热门池取「流行/民谣」段（seed37 起），更贴近真实点歌分布
    hot_source_ids = {f"seed{i}" for i in range(37, 57)}
    hot = [sid for sid, info in info_by_id.items() if info["id"] in hot_source_ids]

    async with factory() as s:
        loaded: dict[tuple[str, int], UserRequest | None] = {}
        new_rows: dict[tuple[str, int], dict] = {}

        async def bump(uid: str, song_id: int, when: datetime, remark: str) -> None:
            """同一批量内安全的置顶+计数：新行放内存、已有行改 ORM 属性，最后统一 flush。"""
            key = (uid, song_id)
            day, week = today_key(when), week_key(when)
            values = new_rows.get(key)
            if values is not None:
                values["time"] = when
                values["day_count"] = values["day_count"] + 1 if values["day"] == day else 1
                values["week_count"] = values["week_count"] + 1 if values["week"] == week else 1
                values["day"], values["week"] = day, week
                return
            if key not in loaded:
                loaded[key] = (
                    await s.execute(
                        select(UserRequest).where(
                            UserRequest.user_id == uid, UserRequest.song_id == song_id
                        )
                    )
                ).scalar_one_or_none()
            row = loaded[key]
            if row is None:
                new_rows[key] = {
                    "user_id": uid,
                    "song_id": song_id,
                    "time": when,
                    "remark": remark,
                    "day": day,
                    "day_count": 1,
                    "week": week,
                    "week_count": 1,
                }
            else:
                row.time = when
                if remark and not row.remark:
                    row.remark = remark
                row.day_count = row.day_count + 1 if row.day == day else 1
                row.week_count = row.week_count + 1 if row.week == week else 1
                row.day, row.week = day, week

        for offset in range(6, 0, -1):  # 6 天前 → 昨天
            day = datetime.now() - timedelta(days=offset)
            for uid in rng.sample(USERS, k=rng.randint(8, 14)):
                for _ in range(rng.randint(1, 2)):
                    song_id = rng.choice(hot if rng.random() < 0.6 else list(info_by_id))
                    when = day.replace(hour=rng.randint(8, 22), minute=rng.randint(0, 59), second=0)
                    await bump(uid, song_id, when, rng.choice(REMARKS))
        s.add_all(UserRequest(**values) for values in new_rows.values())
        await s.commit()

    # 今天：走真实点歌流程（额度检查 / 原子 upsert / 计数）
    perms = Permissions(_PROJECT_ROOT / "data" / "permissions.json")
    requests = RequestService(SongService(), UserService(), perms)
    today_users = rng.sample(USERS, k=12)
    for uid in today_users:
        for _ in range(rng.randint(1, 2)):
            song_id = rng.choice(hot)
            result = await requests.order(uid, info_by_id[song_id])
            if not result.ok and result.reason == "quota":
                break  # 额度用尽则停（与真实行为一致）
    print(f"今日真实点歌流程完成（{len(today_users)} 人参与）")


async def _seed_selected_and_banned() -> None:
    rng = random.Random(7)
    factory = get_session_factory()
    songs = SongService()
    notices = NoticeService()

    # 禁播样例（按 source_id 定位，避免依赖自增 id）
    async with factory() as s:
        banned_rows = (
            await s.execute(select(Song).where(Song.source_id.in_(BANNED_SOURCE_IDS)))
        ).scalars().all()
    for song in banned_rows:
        await songs.set_banned(song.id, True)

    # 选用样例 + 播放历史 + 通知缓存
    async with factory() as s:
        all_ids = list((await s.execute(select(Song.id))).scalars().all())
    banned_ids = {row.id for row in banned_rows}
    picked = rng.sample([sid for sid in all_ids if sid not in banned_ids], SELECTED_COUNT)
    now = datetime.now()
    async with factory() as s:
        for j, sid in enumerate(picked):
            song = await s.get(Song, sid)
            song.selected = True
            s.add(
                PlayHistory(
                    song_id=sid,
                    user_id="",
                    note=f"第 {j + 1} 期节目选用",
                    played_at=now - timedelta(days=j),
                    created_at=now - timedelta(days=j),
                )
            )
        await s.commit()

    # 前 5 首写入选中通知缓存
    async with factory() as s:
        picked_songs = {song.id: song for song in (await s.execute(select(Song).where(Song.id.in_(picked[:5])))).scalars().all()}
    for sid in picked[:5]:
        song = picked_songs[sid]
        await notices.add(sid, song.name, song.artist)
    # 让通知状态更有层次：1 条成功已发、1 条失败放弃、其余待发送
    pending = await notices.pending()
    if pending:
        await notices.mark_attempt(pending[0]["id"], [])
    pending = await notices.pending()
    if pending:
        for _ in range(3):
            await notices.mark_attempt(pending[0]["id"], [pending[0]["user_ids"][0]])
    print(f"已选用 {SELECTED_COUNT} 首、禁播 {len(banned_rows)} 首")


async def main(clear: bool) -> None:
    await init_db()
    if clear:
        await _clear()
    await _seed_users()
    info_by_id = await _seed_songs()
    await _seed_requests(info_by_id)
    await _seed_selected_and_banned()

    factory = get_session_factory()
    async with factory() as s:
        total_requests = len(list((await s.execute(select(UserRequest.id))).scalars().all()))
    print(f"完成：点歌记录共 {total_requests} 条")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="注入点歌演示数据")
    parser.add_argument("--clear", action="store_true", help="先清空业务表再注入")
    args = parser.parse_args()
    asyncio.run(main(args.clear))
