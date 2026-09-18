from .conftest import song_info


async def test_order_first_then_bump(services):
    songs, users, requests = services
    info = song_info()

    r1 = await requests.order("10001", info)
    assert r1.ok and r1.first and r1.used == 1 and r1.limit == 5 and r1.period == "本周"

    r2 = await requests.order("10001", info)
    assert r2.ok and not r2.first and r2.used == 2

    assert await requests.count("10001", "本周") == 2
    assert await requests.count("10001", "今天") == 2


async def test_song_created_once(services):
    songs, _users, requests = services
    info = song_info()
    await requests.order("10001", info)
    await requests.order("10002", info)
    row1 = await songs.get_or_create(info)
    row2 = await songs.get_or_create(info)
    assert row1["id"] == row2["id"]


async def test_banned_song_rejected(services):
    songs, _users, requests = services
    info = song_info()
    row = await songs.get_or_create(info)
    await songs.set_banned(row["id"], True)
    r = await requests.order("10001", info)
    assert not r.ok and r.reason == "banned_song"


async def test_quota_limit(services):
    _songs, _users, requests = services
    for i in range(5):
        r = await requests.order("10001", song_info(sid=f"s{i}"))
        assert r.ok
    r = await requests.order("10001", song_info(sid="s6"))
    assert not r.ok and r.reason == "quota"


async def test_admin_daily_limit(tmp_path, session_factory):
    import json

    from radio.services.permissions import Permissions

    path = tmp_path / "p.json"
    path.write_text(json.dumps({"admins": ["90000"], "super_admins": []}), encoding="utf-8")
    perms = Permissions(path, week_limit=5, admin_daily_limit=99)
    assert perms.role_limit("90000") == ("今天", 99)
    assert perms.role_limit("10001") == ("本周", 5)


async def test_remark_set_and_clear(services):
    songs, _users, requests = services
    await requests.order("10001", song_info())
    row = await songs.get_or_create(song_info())
    assert await requests.set_remark("10001", row["id"], "毕业季必点")
    records = await requests.list_for_user("10001")
    assert records[0]["remark"] == "毕业季必点"
    assert await requests.set_remark("10001", row["id"], "")
    records = await requests.list_for_user("10001")
    assert records[0]["remark"] == ""
    assert not await requests.set_remark("10001", 99999, "x")


async def test_reset_all(services):
    _songs, _users, requests = services
    await requests.order("10001", song_info())
    await requests.order("10001", song_info())
    n = await requests.reset_all()
    assert n >= 1
    assert await requests.count("10001", "本周") == 0
    assert await requests.count("10001", "今天") == 0


async def test_user_ban(services):
    _songs, users, _requests = services
    assert not await users.is_banned("10001")
    assert await users.set_banned("10001", True)
    assert await users.is_banned("10001")
    assert "10001" in await users.list_banned()
    assert await users.set_banned("10001", False)
    assert not await users.is_banned("10001")
    # 解封不存在的用户返回 False；封禁不存在的用户会预创建
    assert not await users.set_banned("99999", False)
    assert await users.set_banned("99999", True)
    assert await users.is_banned("99999")
