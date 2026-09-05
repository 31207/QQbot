"""点歌存储（SQLite）：歌曲库、用户、点歌记录。"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path


class SongRequestStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS songs (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    source     TEXT NOT NULL DEFAULT '',
                    source_id  TEXT NOT NULL DEFAULT '',
                    name       TEXT NOT NULL DEFAULT '',
                    artist     TEXT NOT NULL DEFAULT '',
                    album      TEXT NOT NULL DEFAULT '',
                    cover      TEXT NOT NULL DEFAULT '',
                    duration   INTEGER NOT NULL DEFAULT 0,
                    url        TEXT NOT NULL DEFAULT '',
                    link       TEXT NOT NULL DEFAULT '',
                    is_banned  INTEGER NOT NULL DEFAULT 0,
                    play_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT '',
                    UNIQUE (source, source_id)
                );

                CREATE TABLE IF NOT EXISTS users (
                    user_id    TEXT PRIMARY KEY,
                    is_banned  INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS user_requests (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id    TEXT NOT NULL,
                    song_id    INTEGER NOT NULL REFERENCES songs(id),
                    time       TEXT NOT NULL DEFAULT '',
                    remark     TEXT NOT NULL DEFAULT '',
                    day        TEXT NOT NULL DEFAULT '',
                    day_count  INTEGER NOT NULL DEFAULT 0,
                    UNIQUE (user_id, song_id)
                );
                CREATE INDEX IF NOT EXISTS idx_ur_user ON user_requests(user_id);
                CREATE INDEX IF NOT EXISTS idx_ur_song ON user_requests(song_id);
                """
            )

    def get_or_create_song(self, info: dict) -> dict:
        """按 (source, source_id) 查找歌曲；不存在则初始化 is_banned=0、play_count=0 后入库。"""
        source = str(info.get("source") or "")
        source_id = str(info.get("id") or "")
        now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM songs WHERE source = ? AND source_id = ?",
                (source, source_id),
            ).fetchone()
            if row is None:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO songs
                        (source, source_id, name, artist, album, cover,
                         duration, url, link, is_banned, play_count, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?)
                    """,
                    (
                        source,
                        source_id,
                        str(info.get("name") or ""),
                        str(info.get("artist") or ""),
                        str(info.get("album") or ""),
                        str(info.get("cover") or ""),
                        int(info.get("duration") or 0),
                        str(info.get("url") or ""),
                        str(info.get("link") or ""),
                        now,
                    ),
                )
                row = conn.execute(
                    "SELECT * FROM songs WHERE source = ? AND source_id = ?",
                    (source, source_id),
                ).fetchone()
            return dict(row)

    def ensure_user(self, user_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO users (user_id, created_at) VALUES (?, ?)",
                (user_id, datetime.now().isoformat(timespec="seconds")),
            )

    def get_user(self, user_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
        return dict(row) if row else None

    def is_user_banned(self, user_id: str) -> bool:
        row = self.get_user(user_id)
        return bool(row and row["is_banned"])

    def set_user_banned(self, user_id: str, banned: bool) -> bool:
        """设置用户封禁状态；封禁不存在的用户时直接以封禁状态创建（预封禁）。"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
            if row is None:
                if not banned:
                    return False
                conn.execute(
                    "INSERT INTO users (user_id, is_banned, created_at) VALUES (?, 1, ?)",
                    (user_id, datetime.now().isoformat(timespec="seconds")),
                )
                return True
            conn.execute(
                "UPDATE users SET is_banned = ? WHERE user_id = ?",
                (1 if banned else 0, user_id),
            )
            return True

    def list_banned_users(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT user_id, is_banned, created_at FROM users WHERE is_banned = 1"
            ).fetchall()
        return [dict(r) for r in rows]

    def add_or_bump_request(self, user_id: str, song_id: int) -> bool:
        """点歌入库：首次点歌插入新记录；重复点歌更新时间为当前（置顶）并累计当日次数。

        返回是否为首次点歌。
        """
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        ts = now.isoformat(timespec="seconds")
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, day, day_count FROM user_requests "
                "WHERE user_id = ? AND song_id = ?",
                (user_id, song_id),
            ).fetchone()
            if row is None:
                conn.execute(
                    """
                    INSERT INTO user_requests (user_id, song_id, time, day, day_count)
                    VALUES (?, ?, ?, ?, 1)
                    """,
                    (user_id, song_id, ts, today),
                )
                return True
            day_count = row["day_count"] + 1 if row["day"] == today else 1
            conn.execute(
                "UPDATE user_requests SET time = ?, day = ?, day_count = ? WHERE id = ?",
                (ts, today, day_count, row["id"]),
            )
            return False

    def set_remark(self, user_id: str, song_id: int, remark: str) -> bool:
        """设置/清除用户对某首歌的备注；返回是否命中该用户的点歌记录。"""
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE user_requests SET remark = ? WHERE user_id = ? AND song_id = ?",
                (remark or "", user_id, song_id),
            )
            return cur.rowcount > 0

    def list_for_user(self, user_id: str, limit: int = 20) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT ur.time, ur.remark, s.id AS song_id, s.name, s.artist,
                       s.album, s.cover, s.source
                FROM user_requests ur
                JOIN songs s ON s.id = ur.song_id
                WHERE ur.user_id = ?
                ORDER BY ur.time DESC, ur.id DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def count_for_user_today(self, user_id: str, today: str | None = None) -> int:
        if today is None:
            today = datetime.now().strftime("%Y-%m-%d")
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(day_count), 0) AS n FROM user_requests
                WHERE user_id = ? AND day = ?
                """,
                (user_id, today),
            ).fetchone()
        return int(row["n"]) if row else 0
