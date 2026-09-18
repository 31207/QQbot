"""用户可见文案（帮助菜单 / 用法 / 格式化）。"""

from __future__ import annotations

from radio.util import format_date_cn, format_short_time

HELP_MENU = (
    "点歌机器人功能菜单，回复编号：\n"
    "1. 点歌\n"
    "2. 搜索歌曲\n"
    "3. 我的歌单\n"
    "4. 查询剩余点歌次数\n"
    "5. 备注"
)

HELP_DETAILS = {
    "1": (
        "【点歌】\n"
        "先「搜索 歌名」得到结果，再「点歌 序号」点选；开启后可直接发数字序号选歌\n"
        "例：搜索 晴天 → 点歌 3\n"
        "每周有上限；重复点歌会置顶歌单，本周次数照扣"
    ),
    "2": (
        "【搜索歌曲】\n"
        "「搜索 歌名」全平台搜索；「搜索 平台 歌名」指定平台\n"
        "例：搜索 晴天 / 搜索 qq 晴天\n"
        "支持：网易云、QQ音乐、酷狗、酷我、咪咕、汽水、千千、JOOX、Jamendo、B站\n"
        "开启后直接发送歌名即可搜索；搜索后用「上一页 / 下一页 / 退出搜索」翻页"
    ),
    "5": (
        "【备注】\n"
        "「备注 歌曲编号 内容」为已点歌曲加备注；「备注 歌曲编号」清除备注\n"
        "歌曲编号见「我的歌单」每条后面的 [编号N]"
    ),
}

SEARCH_USAGE = (
    "用法：\n"
    "「搜索 歌名」全平台搜索；「搜索 平台 歌名」指定平台\n"
    "例如：搜索 晴天 / 搜索 qq 晴天\n"
    "支持平台：网易云、QQ音乐、酷狗、酷我、咪咕、汽水、千千、JOOX、Jamendo、B站"
)

FUNCTION_LIST = (
    "—— 你可以这样点歌 ——\n"
    "· 最方便：直接分享一首歌给我，咪帮你搜出来，你确认后就能自动点歌\n"
    "· 搜索 歌名：找歌（如 搜索 晴天 / 搜索 qq 晴天）\n"
    "· 点歌 序号：从结果里点选（如 点歌 3）\n"
    "· 我的歌单：查看你点过的歌\n"
    "· 剩余次数：查今天还能点几首\n"
    "· 备注 编号 内容：给已点歌曲加备注\n"
    "· ID：查看自己的用户ID\n"
    "· 我的信息：查看时间/ID/身份/点歌次数\n"
    "· 帮助：查看功能菜单"
)


def format_order_success(info: dict, first: bool, used: int, limit: int, period: str) -> str:
    name = str(info.get("name") or "未知歌曲")
    artist = str(info.get("artist") or "未知歌手")
    if first:
        return f"点歌成功：{name} - {artist}\n{period}已点 {used}/{limit} 首"
    return f"《{name} - {artist}》已置顶你的歌单\n{period}已点 {used}/{limit} 首"


def format_order_error(reason: str, info: dict, period: str, limit: int) -> str:
    name = str(info.get("name") or "未知歌曲")
    artist = str(info.get("artist") or "未知歌手")
    if reason == "banned_song":
        return f"《{name} - {artist}》已被屏蔽，无法点播"
    next_when = "明天再来吧" if period == "今天" else "下周再来吧"
    return f"{period}点歌次数已用完（{limit} 首），{next_when}"


def format_records(records: list[dict]) -> str:
    if not records:
        return "你还没有点歌记录。先「搜索 歌名」搜索，再「点歌 序号」即可点歌。"
    lines = [f"你的点歌记录（共 {len(records)} 条，最近在前）："]
    for i, r in enumerate(records, 1):
        remark = (r.get("remark") or "").strip()
        line = (
            f"{i}. {r['name']} - {r['artist']} "
            f"[编号{r['song_id']}]（{format_short_time(r.get('time'))}）"
        )
        if remark:
            line += f"\n   备注：{remark}"
        lines.append(line)
    return "\n".join(lines)


def format_remaining(used: int, limit: int, period: str = "本周") -> str:
    return f"{period}已点 {used}/{limit} 首，剩余可点 {max(0, limit - used)} 首。"


def format_profile(now, uid: str, role: str, used: int, limit: int, period: str) -> str:
    return (
        f"时间：{now.year}年{format_date_cn(now)} {now:%H:%M}\n"
        f"用户ID：{uid}\n"
        f"身份：{role}\n"
        f"{period}已点歌：{used}/{limit} 首，剩余 {max(0, limit - used)} 首"
    )


def format_notice_status(pending: list[dict], sent_count: int, failed: list[dict]) -> str:
    lines = [f"通知发送情况：待发送 {len(pending)} 条 / 已发送 {sent_count} 条 / 失败 {len(failed)} 条"]
    if pending:
        lines.append("")
        lines.append("【待发送】")
        for item in pending[:10]:
            date_cn = format_date_cn(item.get("selected_at"))
            retry = f" · 已尝试 {item['attempts']} 轮" if item.get("attempts") else ""
            lines.append(f"· 《{item['name']} - {item['artist']}》（{date_cn}选用）{retry}")
    if failed:
        lines.append("")
        lines.append("【发送失败（已放弃重试）】")
        for item in failed[:10]:
            lines.append(
                f"· 《{item['name']} - {item['artist']}》"
                f"未送达用户：{'、'.join(item['failed_user_ids'])}"
            )
    return "\n".join(lines)
