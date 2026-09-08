"""校园广播站点歌管理后台 —— FastAPI 接口（本地数据版）。

运行：
    .\\.venv\\Scripts\\python.exe web-admin\\backend\\app.py
访问：
    http://127.0.0.1:8600

说明：
- 默认读本地 data/song_requests.db；可用环境变量 WEB_ADMIN_DB 指定库；
  若默认库不存在则自动回退到 web-admin/sample_db/song_requests.db。
- 鉴权：设置环境变量 WEB_ADMIN_TOKEN 后，管理接口需在请求头带
  `Authorization: Bearer <token>`；不设置则不鉴权（本地调试）。
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # qq-bot/
_DEFAULT_DB = _PROJECT_ROOT / "data" / "song_requests.db"
_SAMPLE_DB = Path(__file__).resolve().parent.parent / "sample_db" / "song_requests.db"
_FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
_PERMISSIONS_FILE = _PROJECT_ROOT / "data" / "permissions.json"

_DB = Path(os.environ.get("WEB_ADMIN_DB") or _DEFAULT_DB)
if not _DB.exists() and _SAMPLE_DB.exists():
    _DB = _SAMPLE_DB

ADMIN_TOKEN = os.environ.get("WEB_ADMIN_TOKEN", "")

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


# ---------------------------------------------------------------- 鉴权 ------------------------------------------------


def require_auth(authorization: str = Header(default="")) -> None:
    if not ADMIN_TOKEN:
        return
    if authorization != f"Bearer {ADMIN_TOKEN}":
        raise HTTPException(401, "未授权")


AuthDep = Depends(require_auth)
_auth = {"dependencies": [AuthDep]}


# ---------------------------------------------------------------- 登录 ------------------------------------------------


class LoginIn(BaseModel):
    token: str


@app.post("/api/login")
def login(body: LoginIn):
    if not ADMIN_TOKEN:
        return {"ok": True, "token": ""}
    if body.token == ADMIN_TOKEN:
        return {"ok": True, "token": ADMIN_TOKEN}
    raise HTTPException(401, "token 错误")


# ---------------------------------------------------------------- 点歌池 ------------------------------------------------


@app.get("/api/pool", **_auth)
def get_pool(
    name: str = "",
    user: str = "",
    status: str = "",
    page: int = 1,
    size: int = 20,
):
    page = max(int(page), 1)
    size = min(max(int(size), 1), 200)

    # 查询条件
    where = "WHERE 1=1"
    params: list = []
    if name:
        where += " AND s.name LIKE ?"
        params.append(f"%{name}%")
    if user:
        where += " AND EXISTS (SELECT 1 FROM user_requests ur2 WHERE ur2.song_id=s.id AND ur2.user_id LIKE ?)"
        params.append(f"%{user}%")
    if status == "selected":
        where += " AND s.selected = 1"
    elif status == "banned":
        where += " AND s.is_banned = 1"
    elif status == "pending":
        where += " AND s.selected = 0 AND s.is_banned = 0"

    # 未指定状态时：待选用/禁播在前，已选用排到末尾（内部仍按最近点歌时间倒序）
    order = "ORDER BY s.selected ASC, MAX(ur.time) DESC" if not status else "ORDER BY MAX(ur.time) DESC"

    con = _conn()
    try:
        sql = (
            "SELECT s.id, s.name, s.artist, s.is_banned, s.selected, "
            "COUNT(ur.id) AS req_count, MAX(ur.time) AS last_time "
            "FROM songs s JOIN user_requests ur ON ur.song_id = s.id "
            + where
            + " GROUP BY s.id "
            + order
        )
        total = con.execute(
            "SELECT COUNT(*) AS c FROM (" + sql + ")", params
        ).fetchone()["c"]
        offset = (page - 1) * size
        rows = con.execute(sql + " LIMIT ? OFFSET ?", params + [size, offset]).fetchall()
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
        return {"data": out, "total": total, "page": page, "size": size}
    finally:
        con.close()


@app.get("/api/songs/{sid}/requests", **_auth)
def get_song_requests(sid: int):
    con = _conn()
    try:
        rows = con.execute(
            """
            SELECT ur.user_id, ur.time, ur.remark, ur.day_count, s.name, s.artist
            FROM user_requests ur JOIN songs s ON s.id = ur.song_id
            WHERE ur.song_id = ? ORDER BY ur.time DESC
            """,
            (sid,),
        ).fetchall()
        return {"data": [dict(r) for r in rows]}
    finally:
        con.close()


class SelectManyIn(BaseModel):
    ids: list[int]
    note: str = ""


@app.post("/api/songs/select_many", **_auth)
def select_many(body: SelectManyIn):
    now = datetime.now().isoformat(timespec="seconds")
    con = _conn()
    try:
        rows = con.execute(
            f"SELECT id FROM songs WHERE id IN ({','.join('?' * len(body.ids))})",
            body.ids,
        ).fetchall()
    finally:
        con.close()
    for row in rows:
        _exec_write("UPDATE songs SET selected = 1 WHERE id = ?", (row["id"],))
        _exec_write(
            "INSERT INTO play_history (song_id, user_id, note, played_at, created_at) "
            "VALUES (?, '', ?, ?, ?)",
            (row["id"], body.note, now, now),
        )
    return {"ok": True, "count": len(rows)}


class SelectIn(BaseModel):
    user_id: str = ""
    note: str = ""


@app.post("/api/songs/{sid}/select", **_auth)
def select_song(sid: int, body: SelectIn):
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


@app.post("/api/songs/{sid}/ban", **_auth)
def ban_song(sid: int):
    _exec_write("UPDATE songs SET is_banned = 1 WHERE id = ?", (sid,))
    return {"ok": True}


@app.post("/api/songs/{sid}/unban", **_auth)
def unban_song(sid: int):
    _exec_write("UPDATE songs SET is_banned = 0 WHERE id = ?", (sid,))
    return {"ok": True}


# ---------------------------------------------------------------- 用户 ------------------------------------------------


@app.get("/api/users", **_auth)
def get_users():
    today = datetime.now().strftime("%Y-%m-%d")
    con = _conn()
    try:
        rows = con.execute("SELECT user_id, is_banned, created_at FROM users").fetchall()
        out = []
        for r in rows:
            today_count = con.execute(
                "SELECT COALESCE(SUM(day_count),0) c FROM user_requests "
                "WHERE user_id = ? AND day = ?",
                (r["user_id"], today),
            ).fetchone()["c"]
            out.append(
                {
                    "user_id": r["user_id"],
                    "is_banned": bool(r["is_banned"]),
                    "created_at": r["created_at"],
                    "today_count": today_count,
                }
            )
        return {"data": out}
    finally:
        con.close()


@app.post("/api/users/{uid}/ban", **_auth)
def ban_user(uid: str):
    _exec_write(
        "INSERT INTO users (user_id, is_banned, created_at) VALUES (?, 1, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET is_banned = 1",
        (uid, datetime.now().isoformat(timespec="seconds")),
    )
    return {"ok": True}


@app.post("/api/users/{uid}/unban", **_auth)
def unban_user(uid: str):
    _exec_write("UPDATE users SET is_banned = 0 WHERE user_id = ?", (uid,))
    return {"ok": True}


# ---------------------------------------------------------------- 播放历史 ------------------------------------------------


@app.get("/api/history", **_auth)
def get_history(name: str = "", date: str = "", page: int = 1, size: int = 20):
    page = max(int(page), 1)
    size = min(max(int(size), 1), 200)
    con = _conn()
    try:
        sql = (
            "SELECT ph.id, ph.song_id, s.name, s.artist, ph.user_id, "
            "ph.note, ph.played_at "
            "FROM play_history ph JOIN songs s ON s.id = ph.song_id WHERE 1=1"
        )
        params: list = []
        if name:
            sql += " AND s.name LIKE ?"
            params.append(f"%{name}%")
        if date:
            sql += " AND ph.played_at LIKE ?"
            params.append(f"{date}%")
        sql += " ORDER BY ph.played_at DESC"
        total = con.execute(
            "SELECT COUNT(*) AS c FROM (" + sql + ")", params
        ).fetchone()["c"]
        offset = (page - 1) * size
        rows = con.execute(sql + " LIMIT ? OFFSET ?", params + [size, offset]).fetchall()
        return {"data": [dict(r) for r in rows], "total": total, "page": page, "size": size}
    finally:
        con.close()


def _reset_songs_by_history_ids(ids: list[int]) -> int:
    """删除指定播放历史后，把对应歌曲的 selected 重置为 0（回到待选用）。

    先取受影响歌曲 id（去重），再清空这些歌曲的历史记录，最后重置选中状态。
    返回被重置的歌曲数。
    """
    if not ids:
        return 0
    placeholders = ",".join("?" * len(ids))
    con = _conn()
    try:
        rows = con.execute(
            f"SELECT DISTINCT song_id FROM play_history WHERE id IN ({placeholders})",
            ids,
        ).fetchall()
    finally:
        con.close()
    song_ids = list({r["song_id"] for r in rows})
    # 事务性写入：删历史 + 重置选中状态
    _exec_write(
        f"DELETE FROM play_history WHERE id IN ({placeholders})",
        tuple(ids),
    )
    if song_ids:
        for sid in song_ids:
            _exec_write("UPDATE songs SET selected = 0 WHERE id = ?", (sid,))
    return len(song_ids)


@app.delete("/api/history/{hid}", **_auth)
def delete_history_one(hid: int):
    con = _conn()
    try:
        row = con.execute("SELECT id FROM play_history WHERE id = ?", (hid,)).fetchone()
    finally:
        con.close()
    if not row:
        raise HTTPException(404, "播放历史不存在")
    n = _reset_songs_by_history_ids([hid])
    return {"ok": True, "reset_songs": n}


class HistoryDeleteManyIn(BaseModel):
    ids: list[int]


@app.post("/api/history/delete_many", **_auth)
def delete_history_many(body: HistoryDeleteManyIn):
    if not body.ids:
        return {"ok": True, "count": 0, "reset_songs": 0}
    n = _reset_songs_by_history_ids(body.ids)
    return {"ok": True, "count": len(body.ids), "reset_songs": n}


@app.post("/api/history/delete_all", **_auth)
def delete_history_all():
    con = _conn()
    try:
        rows = con.execute("SELECT id, song_id FROM play_history").fetchall()
    finally:
        con.close()
    song_ids = list({r["song_id"] for r in rows})
    _exec_write("DELETE FROM play_history", ())
    for sid in song_ids:
        _exec_write("UPDATE songs SET selected = 0 WHERE id = ?", (sid,))
    return {"ok": True, "count": len(rows), "reset_songs": len(song_ids)}


# ---------------------------------------------------------------- 统计 ------------------------------------------------


@app.get("/api/stats", **_auth)
def get_stats():
    con = _conn()
    try:
        total = con.execute("SELECT COUNT(*) c FROM user_requests").fetchone()["c"]
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
        hot = [
            dict(r)
            for r in con.execute(
                """
                SELECT s.name, s.artist, COUNT(ur.id) AS cnt
                FROM user_requests ur JOIN songs s ON s.id = ur.song_id
                GROUP BY s.id ORDER BY cnt DESC LIMIT 10
                """
            ).fetchall()
        ]
        trend = [
            dict(r)
            for r in con.execute(
                "SELECT day, COUNT(*) AS cnt FROM user_requests GROUP BY day ORDER BY day"
            ).fetchall()
        ]
        return {
            "data": {
                "total": total,
                "requests": requests,
                "pending": pending,
                "selected": selected,
                "banned": banned,
                "hot": hot,
                "trend": trend,
            }
        }
    finally:
        con.close()


# ---------------------------------------------------------------- 权限白名单 ------------------------------------------------


def _read_permissions() -> dict:
    try:
        return json.loads(_PERMISSIONS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"admins": [], "super_admins": []}


@app.get("/api/permissions", **_auth)
def get_permissions():
    return {"data": _read_permissions()}


class PermissionsIn(BaseModel):
    admins: list[str]
    super_admins: list[str]


@app.put("/api/permissions", **_auth)
def put_permissions(body: PermissionsIn):
    data = {"admins": [str(x) for x in body.admins], "super_admins": [str(x) for x in body.super_admins]}
    try:
        _PERMISSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        _PERMISSIONS_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return {"ok": True}
    except Exception as exc:  # pragma: no cover
        raise HTTPException(500, f"写入白名单失败: {exc}")


# 托管前端静态文件（需放在最后，避免覆盖 /api/*）
app.mount("/", StaticFiles(directory=str(_FRONTEND), html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("WEB_ADMIN_PORT", "8600")))
