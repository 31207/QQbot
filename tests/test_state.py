import asyncio
import time

from radio.state import StateStore


def test_search_session_ttl():
    store = StateStore(session_ttl=0.05)
    store.set_search("u1", _session())
    assert store.search_session("u1") is not None
    time.sleep(0.08)
    assert store.search_session("u1") is None


def test_sweep_removes_stale_users():
    store = StateStore(session_ttl=0.05, memory_ttl=0.05)
    store.user("u1").touched = time.time() - 10
    store.user("u2")
    assert store.sweep() == 1
    assert "u1" not in store._users
    assert "u2" in store._users


def test_memory_prune():
    store = StateStore(memory_ttl=3600, memory_turns=3)
    for i in range(5):
        store.push_memory("u1", "user", f"m{i}")
    mem = store.memory("u1")
    assert [m["content"] for m in mem] == ["m2", "m3", "m4"]


def test_memory_ttl_expiry():
    store = StateStore(memory_ttl=0.05)
    store.push_memory("u1", "user", "old")
    time.sleep(0.08)
    assert store.memory("u1") == []


def test_pending_share_ttl():
    store = StateStore(session_ttl=0.05)
    store.set_pending_share("u1", {"name": "晴天"})
    assert store.pending_share("u1")["name"] == "晴天"
    time.sleep(0.08)
    assert store.pending_share("u1") is None


def _session():
    from radio.state import SearchSession

    return SearchSession(query="晴天", source=None, songs=[{"name": "晴天"}], page=1, total_pages=1)
