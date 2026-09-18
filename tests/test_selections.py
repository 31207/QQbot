from datetime import datetime

from radio.db.models import PlayHistory
from radio.services.selections import SelectionService

from .conftest import song_info


async def _select(session_factory, song_id: int, at: datetime) -> None:
    async with session_factory() as s:
        s.add(
            PlayHistory(song_id=song_id, user_id="", note="", played_at=at, created_at=at)
        )
        await s.commit()


async def test_empty_when_not_selected(session_factory, services):
    _songs, _users, requests = services
    await requests.order("u1", song_info())
    assert await SelectionService(session_factory).list_for_user("u1") == []


async def test_lists_selected_song(session_factory, services):
    songs, _users, requests = services
    info = song_info()
    row = await songs.get_or_create(info)
    await requests.order("u1", info)
    await _select(session_factory, row["id"], datetime(2026, 9, 1, 12, 0))

    records = await SelectionService(session_factory).list_for_user("u1")
    assert len(records) == 1
    assert records[0]["name"] == "晴天"
    assert records[0]["selected_at"] == datetime(2026, 9, 1, 12, 0)


async def test_orders_recent_first_and_dedups(session_factory, services):
    songs, _users, requests = services
    info_a = song_info(sid="001", name="晴天")
    info_b = song_info(sid="002", name="稻香")
    row_a = await songs.get_or_create(info_a)
    row_b = await songs.get_or_create(info_b)
    await requests.order("u1", info_a)
    await requests.order("u1", info_b)

    await _select(session_factory, row_a["id"], datetime(2026, 9, 1, 9, 0))
    await _select(session_factory, row_a["id"], datetime(2026, 9, 3, 9, 0))
    await _select(session_factory, row_b["id"], datetime(2026, 9, 2, 9, 0))

    records = await SelectionService(session_factory).list_for_user("u1")
    assert [r["name"] for r in records] == ["晴天", "稻香"]
    assert records[0]["selected_at"] == datetime(2026, 9, 3, 9, 0)


async def test_excludes_other_users_and_limit(session_factory, services):
    songs, _users, requests = services
    info_a = song_info(sid="001", name="晴天")
    info_b = song_info(sid="002", name="稻香")
    row_a = await songs.get_or_create(info_a)
    row_b = await songs.get_or_create(info_b)
    await requests.order("u1", info_a)
    await requests.order("u2", info_b)
    await _select(session_factory, row_a["id"], datetime(2026, 9, 1, 9, 0))
    await _select(session_factory, row_b["id"], datetime(2026, 9, 2, 9, 0))

    service = SelectionService(session_factory)
    assert [r["name"] for r in await service.list_for_user("u1")] == ["晴天"]
    assert [r["name"] for r in await service.list_for_user("u2")] == ["稻香"]
    assert await service.list_for_user("u2", limit=0) == []
