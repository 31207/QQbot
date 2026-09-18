from radio.services.notices import MAX_ATTEMPTS, NoticeService

from .conftest import song_info


async def _order_for_users(requests, uids, info):
    for uid in uids:
        await requests.order(uid, info)


async def _make_notice(session_factory, services, uids=("10001", "10002")):
    songs, _users, requests = services
    info = song_info()
    row = await songs.get_or_create(info)
    await _order_for_users(requests, uids, info)
    notices = NoticeService(session_factory)
    return notices, row, info


async def test_add_skips_when_no_requesters(session_factory, services):
    songs, _users, _requests = services
    row = await songs.get_or_create(song_info())
    notices = NoticeService(session_factory)
    assert not await notices.add(row["id"], "晴天", "周杰伦")
    assert await notices.pending_count() == 0


async def test_pending_first_round_all_users(session_factory, services):
    notices, row, info = await _make_notice(session_factory, services)
    assert await notices.add(row["id"], info["name"], info["artist"])
    pending = await notices.pending()
    assert len(pending) == 1
    assert sorted(pending[0]["user_ids"]) == ["10001", "10002"]
    assert await notices.pending_count() == 1


async def test_retry_only_failed_users(session_factory, services):
    notices, row, info = await _make_notice(session_factory, services)
    await notices.add(row["id"], info["name"], info["artist"])
    notice_id = (await notices.pending())[0]["id"]

    await notices.mark_attempt(notice_id, ["10002"])
    pending = await notices.pending()
    assert pending[0]["user_ids"] == ["10002"]

    await notices.mark_attempt(notice_id, [])
    assert await notices.pending_count() == 0
    pending, sent, failed = await notices.status()
    assert pending == [] and sent == 1 and failed == []


async def test_give_up_after_max_attempts(session_factory, services):
    notices, row, info = await _make_notice(session_factory, services)
    await notices.add(row["id"], info["name"], info["artist"])
    notice_id = (await notices.pending())[0]["id"]

    for _ in range(MAX_ATTEMPTS):
        await notices.mark_attempt(notice_id, ["10002"])
    assert await notices.pending_count() == 0
    pending, sent, failed = await notices.status()
    assert pending == [] and sent == 0
    assert failed[0]["failed_user_ids"] == ["10002"]


async def test_status_groups(session_factory, services):
    notices, row, info = await _make_notice(session_factory, services)
    await notices.add(row["id"], info["name"], info["artist"])
    notice_id = (await notices.pending())[0]["id"]
    await notices.mark_attempt(notice_id, [])

    songs, _users, requests = services
    info2 = song_info(sid="002", name="稻香")
    row2 = await songs.get_or_create(info2)
    await _order_for_users(requests, ("10003",), info2)
    await notices.add(row2["id"], info2["name"], info2["artist"])
    notice2_id = (await notices.pending())[0]["id"]
    for _ in range(MAX_ATTEMPTS):
        await notices.mark_attempt(notice2_id, ["10003"])

    pending, sent, failed = await notices.status()
    assert sent == 1
    assert pending == []
    assert len(failed) == 1 and failed[0]["name"] == "稻香"
