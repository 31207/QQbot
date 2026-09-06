"""校园广播站点歌管理后台 —— 本地数据版（预留 REST 接口）。

运行：
    .\\.venv\\Scripts\\python.exe web-admin\\backend\\app.py
访问：
    http://127.0.0.1:8600

说明：当前直接读写本地 data/song_requests.db，接口结构即后续要接的最终结构。
"""

from __future__ import annotations

import sqlite3
import time
from datetime import datetime
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # qq-bot/
_DEFAULT_DB = _PROJECT_ROOT / "data" / "song_requests.db"
_SAMPLE_DB = Path(__file__).resolve().parent.parent / "sample_db" / "song_requests.db"
_DB = Path(os.environ.get("WEB_ADMIN_DB") or _DEFAULT_DB)
if not _DB.exists() and _SAMPLE_DB.exists():
    _DB = _SAMPLE_DB
_FRONTEND = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(title="校园广播站点歌管理后台")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(str(_DB), check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def _migrate() -> None:
    """幂等迁移：songs.selected + play_history 表。"""
    con = _conn()
    try:
        con.execute("PRAGMA journal_mode=WAL;")
        cols = [r["name"] for r in con.execute("PRAGMA table_info(songs)")]
        if "selected" not in cols:
            con.execute(
                "ALTER TABLE songs ADD COLUMN selected INTEGER NOT NULL DEFAULT 0"
            )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS play_history (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                song_id    INTEGER NOT NULL REFERENCES songs(id),
                user_id    TEXT DEFAULT '',
                note       TEXT DEFAULT '',
                played_at  TEXT DEFAULT '',
                created_at TEXT DEFAULT ''
            )
            """
        )
        con.commit()
    finally:
        con.close()


_migrate()


def _exec_write(sql: str, params: tuple) -> None:
    """写库（带“database locked”重试）。"""
    for attempt in range(6):
        con = _conn()
        try:
            con.execute("PRAGMA journal_mode=WAL;")
            con.execute(sql, params)
            con.commit()
            return
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() or attempt == 5:
                raise
            time.sleep(0.4 * (attempt + 1))
        finally:
            con.close()


@app.get("/api/pool")
def get_pool():
    """点歌池：所有被点过的歌（含点歌人、次数、是否禁播/已选用）。"""
    con = _conn()
    try:
        rows = con.execute(
            """
            SELECT s.id, s.name, s.artist, s.is_banned, s.selected,
                   COUNT(ur.id) AS req_count, MAX(ur.time) AS last_time
            FROM songs s JOIN user_requests ur ON ur.song_id = s.id
            GROUP BY s.id
            ORDER BY last_time DESC
            """
        ).fetchall()
        out = []
        for r in rows:
            reqs = con.execute(
                "SELECT DISTINCT user_id FROM user_requests WHERE song_id = ?",
                (r["id"],),
            ).fetchall()
            out.append(
                {
                    "id": r["id"],
                    "name": r["name"],
                    "artist": r["artist"],
                    "is_banned": bool(r["is_banned"]),
                    "selected": bool(r["selected"]),
                    "req_count": r["req_count"],
                    "last_time": r["last_time"],
                    "requesters": [x["user_id"] for x in reqs],
                }
            )
        return {"data": out}
    finally:
        con.close()


@app.get("/api/history")
def get_history():
    """播放历史。"""
    con = _conn()
    try:
        rows = con.execute(
            """
            SELECT ph.id, ph.song_id, s.name, s.artist, ph.user_id,
                   ph.note, ph.played_at
            FROM play_history ph JOIN songs s ON s.id = ph.song_id
            ORDER BY ph.played_at DESC
            """
        ).fetchall()
        return {"data": [dict(r) for r in rows]}
    finally:
        con.close()


@app.get("/api/stats")
def get_stats():
    con = _conn()
    try:
        total = con.execute(
            "SELECT COUNT(*) c FROM user_requests"
        ).fetchone()["c"]
        requests = con.execute(
            "SELECT COUNT(DISTINCT song_id) c FROM user_requests"
        ).fetchone()["c"]
        selected = con.execute(
            "SELECT COUNT(*) c FROM songs WHERE selected = 1"
        ).fetchone()["c"]
        banned = con.execute(
            "SELECT COUNT(*) c FROM songs WHERE is_banned = 1"
        ).fetchone()["c"]
        pending = con.execute(
            """
            SELECT COUNT(*) c FROM songs s
            WHERE s.selected = 0 AND s.is_banned = 0
              AND EXISTS (SELECT 1 FROM user_requests ur WHERE ur.song_id = s.id)
            """
        ).fetchone()["c"]
        return {
            "data": {
                "total": total,
                "requests": requests,
                "pending": pending,
                "selected": selected,
                "banned": banned,
            }
        }
    finally:
        con.close()


class SelectIn(BaseModel):
    user_id: str = ""
    note: str = ""


@app.post("/api/songs/{sid}/ban")
def ban_song(sid: int):
    _exec_write("UPDATE songs SET is_banned = 1 WHERE id = ?", (sid,))
    return {"ok": True}


@app.post("/api/songs/{sid}/unban")
def unban_song(sid: int):
    _exec_write("UPDATE songs SET is_banned = 0 WHERE id = ?", (sid,))
    return {"ok": True}


@app.post("/api/songs/{sid}/select")
def select_song(sid: int, body: SelectIn):
    """选用：标记歌曲已选用，并记入播放历史。"""
    con = _conn()
    try:
        row = con.execute("SELECT id FROM songs WHERE id = ?", (sid,)).fetchone()
        if not row:
            raise HTTPException(404, "歌曲不存在")
    finally:
        con.close()
    now = datetime.now().isoformat(timespec="seconds")
    _exec_write("UPDATE songs SET selected = 1 WHERE id = ?", (sid,))
    _exec_write(
        "INSERT INTO play_history (song_id, user_id, note, played_at, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (sid, body.user_id, body.note, now, now),
    )
    return {"ok": True}


# 托管前端静态文件（需放在最后，避免覆盖 /api/*）
app.mount("/", StaticFiles(directory=str(_FRONTEND), html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8600)
