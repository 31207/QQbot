"""点歌记录存储（SQLite）。"""

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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS song_requests (
                    id      INTEGER PRIMARY KEY AUTOINCREMENT,
                    time    TEXT NOT NULL,
                    scene   TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    song    TEXT NOT NULL,
                    artist  TEXT NOT NULL DEFAULT '',
                    raw     TEXT NOT NULL DEFAULT '',
                    msg_id  TEXT
                )
                """
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_song_msg ON song_requests(msg_id)"
            )

    def append(
        self,
        scene: str,
        user_id: str,
        song: str,
        artist: str = "",
        raw: str = "",
        msg_id: str | None = None,
        ts: datetime | None = None,
    ) -> bool:
        ts = ts or datetime.now()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO song_requests
                    (time, scene, user_id, song, artist, raw, msg_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ts.isoformat(timespec="seconds"),
                    scene,
                    user_id or "",
                    song,
                    artist or "",
                    raw or "",
                    msg_id,
                ),
            )
            return cur.rowcount > 0

    def list_for_user(self, user_id: str, limit: int = 20) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT time, scene, user_id, song, artist, raw, msg_id
                FROM song_requests
                WHERE user_id = ?
                ORDER BY id DESC
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
                SELECT COUNT(*) AS n
                FROM song_requests
                WHERE user_id = ? AND substr(time, 1, 10) = ?
                """,
                (user_id, today),
            ).fetchone()
        return int(row["n"]) if row else 0
