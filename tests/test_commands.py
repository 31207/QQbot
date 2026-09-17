from qqbot.plugins.qq_music_bot.commands import CommandKind, parse_command


def test_search_basic():
    cmd = parse_command("搜索 晴天")
    assert cmd.kind == CommandKind.SEARCH
    assert cmd.args == (None, "晴天")


def test_search_with_platform():
    cmd = parse_command("搜索 qq 晴天")
    assert cmd.args == ("qq", "晴天")


def test_search_empty_keyword():
    cmd = parse_command("搜索")
    assert cmd.kind == CommandKind.SEARCH
    assert cmd.args == (None, "")


def test_order():
    assert parse_command("点歌 3").args == (3,)
    assert parse_command("点歌").args == (None,)
    assert parse_command("点歌 abc") is None


def test_remark():
    assert parse_command("备注 12 好听").args == (12, "好听")
    assert parse_command("备注 12").args == (12, "")
    assert parse_command("备注").args == (None, None)


def test_admin_commands():
    assert parse_command("封禁 12345").args == ("12345",)
    assert parse_command("解封 12345").args == ("12345",)
    assert parse_command("封禁列表").kind == CommandKind.BAN_LIST
    assert parse_command("解封列表").kind == CommandKind.BAN_LIST
    assert parse_command("禁歌 晴天").args == ("晴天",)
    assert parse_command("解禁歌 晴天").args == ("晴天",)
    assert parse_command("重置点歌次数").kind == CommandKind.RESET_QUOTA
    assert parse_command("重置").kind == CommandKind.RESET_QUOTA


def test_notice_commands():
    for text in ("通知状态", "通知情况", "通知列表"):
        assert parse_command(text).kind == CommandKind.NOTICE_STATUS
    for text in ("发送通知", "通知发送", "立即发送通知"):
        assert parse_command(text).kind == CommandKind.NOTICE_SEND


def test_list_and_remaining():
    for text in ("我的歌单", "歌单", "点歌记录", "查看我的点歌记录", "我的点歌记录"):
        assert parse_command(text).kind == CommandKind.MY_SONGS
    for text in ("剩余次数", "查询剩余点歌次数", "剩余点歌次数"):
        assert parse_command(text).kind == CommandKind.REMAINING


def test_help():
    assert parse_command("帮助").kind == CommandKind.HELP
    assert parse_command("菜单").kind == CommandKind.HELP


def test_pagination():
    assert parse_command("上一页").kind == CommandKind.SEARCH_PREV
    assert parse_command("下一页").kind == CommandKind.SEARCH_NEXT
    assert parse_command("退出搜索").kind == CommandKind.SEARCH_EXIT


def test_unknown_is_none():
    assert parse_command("你好") is None
    assert parse_command("") is None
    assert parse_command("/搜索 晴天").args == (None, "晴天")
