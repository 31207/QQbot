"""进程内会话状态（每用户），带 TTL 自动回收，杜绝内存泄漏。

- 搜索会话（含翻页）、一次性功能模式、帮助菜单选择、分享待点、LLM 多轮记忆。
- 任何交互都会刷新 ``touched``；后台维护任务定期调用 :meth:`StateStore.sweep`
  清理过期用户；用户总数有硬上限，超出时淘汰最久未活动者。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class SearchSession:
    query: str
    source: str | None
    songs: list[dict]
    page: int = 1
    total_pages: int = 1

    def page_songs(self, page_size: int) -> list[dict]:
        start = (self.page - 1) * page_size
        return self.songs[start : start + page_size]


@dataclass
class UserState:
    search: SearchSession | None = None
    help_pending: bool = False
    pending_mode: str | None = None
    pending_order: bool = False
    pending_share: dict | None = None
    pending_share_ts: float = 0.0
    memory: list[dict] = field(default_factory=list)
    touched: float = field(default_factory=time.time)


class StateStore:
    def __init__(
        self,
        session_ttl: float = 600.0,
        memory_ttl: float = 1800.0,
        memory_turns: int = 12,
        max_users: int = 4096,
    ) -> None:
        self.session_ttl = session_ttl
        self.memory_ttl = memory_ttl
        self.memory_turns = memory_turns
        self.max_users = max_users
        self._users: dict[str, UserState] = {}

    # ---------------------------------------------------------------- 基础

    def user(self, uid: str) -> UserState:
        state = self._users.get(uid)
        if state is None:
            state = UserState()
            self._users[uid] = state
        state.touched = time.time()
        return state

    def sweep(self) -> int:
        """清理过期用户与记忆；返回清除的用户数。"""
        now = time.time()
        expire_after = max(self.session_ttl, self.memory_ttl)
        removed = 0
        for uid in [u for u, s in self._users.items() if now - s.touched > expire_after]:
            self._users.pop(uid, None)
            removed += 1
        overflow = len(self._users) - self.max_users
        if overflow > 0:
            oldest = sorted(self._users, key=lambda u: self._users[u].touched)[:overflow]
            for uid in oldest:
                self._users.pop(uid, None)
                removed += 1
        for state in self._users.values():
            state.memory[:] = [m for m in state.memory if now - m["ts"] <= self.memory_ttl]
        return removed

    # ---------------------------------------------------------------- 搜索会话

    def search_session(self, uid: str) -> SearchSession | None:
        state = self._users.get(uid)
        if state is None or state.search is None:
            return None
        if time.time() - state.touched > self.session_ttl:
            return None
        state.touched = time.time()
        return state.search

    def set_search(self, uid: str, session: SearchSession) -> None:
        state = self.user(uid)
        state.search = session
        state.touched = time.time()

    def clear_search(self, uid: str) -> None:
        state = self._users.get(uid)
        if state is not None:
            state.search = None

    # ---------------------------------------------------------------- 分享待点

    def pending_share(self, uid: str) -> dict | None:
        state = self._users.get(uid)
        if state is None or state.pending_share is None:
            return None
        if time.time() - state.pending_share_ts > self.session_ttl:
            state.pending_share = None
            return None
        return state.pending_share

    def set_pending_share(self, uid: str, info: dict) -> None:
        state = self.user(uid)
        state.pending_share = info
        state.pending_share_ts = time.time()

    def clear_pending_share(self, uid: str) -> None:
        state = self._users.get(uid)
        if state is not None:
            state.pending_share = None

    # ---------------------------------------------------------------- LLM 记忆

    def memory(self, uid: str) -> list[dict]:
        """返回 [{role, content}]（已按 TTL / 条数裁剪）。"""
        state = self._users.get(uid)
        if state is None:
            return []
        now = time.time()
        items = [m for m in state.memory if now - m["ts"] <= self.memory_ttl]
        state.memory = items
        return [{"role": m["role"], "content": m["content"]} for m in items[-self.memory_turns :]]

    def push_memory(self, uid: str, role: str, content: str) -> None:
        if not content:
            return
        state = self.user(uid)
        state.memory.append({"role": role, "content": content, "ts": time.time()})
