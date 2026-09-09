"""校园广播站点歌管理后台 —— FastAPI 接口（数据版，SQLAlchemy 支持 SQLite / PostgreSQL）。

运行：
    .\\.venv\\Scripts\\python.exe web-admin\\backend\\app.py
访问：
    http://127.0.0.1:8600

说明：
- 数据由统一 db 层（db.py）从 DATABASE_URL 读取：未设置时本地 SQLite
  data/song_requests.db；设置 PostgreSQL 连接串即切换到 PG。
- 兼容旧环境变量 WEB_ADMIN_DB（指定 SQLite 文件路径），在未设 DATABASE_URL 时生效。
- 鉴权：设置环境变量 WEB_ADMIN_USERNAME / WEB_ADMIN_PASSWORD 后，管理接口需先
  `POST /api/login`（账号+密码）拿 token，再带 `Authorization: Bearer <token>`。
  两者都不设置则不鉴权（本地调试）。旧 `WEB_ADMIN_TOKEN` 仍兼容（作 token 登录）。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # 项目根，供 import db

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # qq-bot/
_SAMPLE_DB = Path(__file__).resolve().parent.parent / "sample_db" / "song_requests.db"
_FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
_PERMISSIONS_FILE = _PROJECT_ROOT / "data" / "permissions.json"

# 兼容旧 WEB_ADMIN_DB：在未设 DATABASE_URL 时，用它指向本地 sqlite 文件。
if not os.environ.get("DATABASE_URL"):
    _legacy = Path(os.environ.get("WEB_ADMIN_DB") or (_PROJECT_ROOT / "data" / "song_requests.db"))
    if not _legacy.exists() and _SAMPLE_DB.exists():
        _legacy = _SAMPLE_DB
    os.environ["DATABASE_URL"] = f"sqlite:///{_legacy.as_posix()}"

ADMIN_USERNAME = os.environ.get("WEB_ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("WEB_ADMIN_PASSWORD", "")
ADMIN_TOKEN = os.environ.get("WEB_ADMIN_TOKEN", "")

from db import (  # noqa: E402  (需先处理 DATABASE_URL)
    PlayHistory,
    SessionLocal,
    Song,
    SongSelectedNotice,
    User,
    UserRequest,
    init_db,
)

init_db()


app = FastAPI(title="校园广播站点歌管理后台")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _session() -> Session:
    return SessionLocal()


def _record_selected_notice(sess: Session, song_id: int, name: str, artist: str) -> None:
    """歌曲被选用后，写入一条待通知缓存（含该歌所有点歌用户，去重）。

    只写缓存不发送：由 bot 端定时任务读取后逐用户私聊通知。
    """
    from sqlalchemy import select as _select

    import json as _json

    uids = list(
        sess.execute(
            _select(UserRequest.user_id)
            .where(UserRequest.song_id == song_id)
            .distinct()
        ).scalars().all()
    )
    if not uids:
        return
    sess.add(
        SongSelectedNotice(
            song_id=song_id,
            name=name,
            artist=artist,
            selected_at=datetime.now().isoformat(timespec="seconds"),
            user_ids=_json.dumps(list(dict.fromkeys(uids)), ensure_ascii=False),
            sent=False,
            sent_at="",
        )
    )


# ---------------------------------------------------------------- 鉴权 ------------------------------------------------


def require_auth(authorization: str = Header(default="")) -> None:
    if not ADMIN_PASSWORD and not ADMIN_TOKEN:
        return
    expect = f"Bearer {_session_token()}" if ADMIN_PASSWORD else f"Bearer {ADMIN_TOKEN}"
    if authorization != expect:
        raise HTTPException(401, "未授权")


AuthDep = Depends(require_auth)
_auth = {"dependencies": [AuthDep]}


# ---------------------------------------------------------------- 登录 ------------------------------------------------


class LoginIn(BaseModel):
    username: str
    password: str


def _session_token() -> str:
    """由账号+密码生成稳定会话 token（无状态，改密码即失效）。"""
    if not ADMIN_PASSWORD:
        return ""
    key = (ADMIN_PASSWORD or "").encode()
    msg = (ADMIN_USERNAME or "admin").encode()
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


@app.post("/api/login")
def login(body: LoginIn):
    if not ADMIN_PASSWORD and not ADMIN_TOKEN:
        return {"ok": True, "token": ""}
    if ADMIN_PASSWORD:
        if body.username == ADMIN_USERNAME and body.password == ADMIN_PASSWORD:
            return {"ok": True, "token": _session_token()}
        raise HTTPException(401, "账号或密码错误")
    # 旧 token 登录兜底
    if body.password == ADMIN_TOKEN:
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

    with _session() as s:
        # 点歌池只看被点过的歌：songs 上存在至少一条 user_requests
        sub_agg = (
            select(
                UserRequest.song_id,
                func.count(UserRequest.id).label("req_count"),
                func.max(UserRequest.time).label("last_time"),
            )
            .group_by(UserRequest.song_id)
            .subquery()
        )
        stmt = (
            select(
                Song.id,
                Song.name,
                Song.artist,
                Song.is_banned,
                Song.selected,
                sub_agg.c.req_count,
                sub_agg.c.last_time,
            )
            .join(sub_agg, sub_agg.c.song_id == Song.id)
        )
        conds = []
        if name:
            conds.append(Song.name.like(f"%{name}%"))
        if user:
            conds.append(
                Song.id.in_(
                    select(UserRequest.song_id).where(UserRequest.user_id.like(f"%{user}%"))
                )
            )
        if status == "selected":
            conds.append(Song.selected.is_(True))
        elif status == "banned":
            conds.append(Song.is_banned.is_(True))
        elif status == "pending":
            conds.append(Song.selected.is_(False))
            conds.append(Song.is_banned.is_(False))
        if conds:
            stmt = stmt.where(*conds)

        total = s.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        if not status:
            # 默认：待选用/禁播在前，已选用排末尾；组内按最近点歌时间倒序
            stmt = stmt.order_by(Song.selected.asc(), sub_agg.c.last_time.desc())
        else:
            stmt = stmt.order_by(sub_agg.c.last_time.desc())
        stmt = stmt.limit(size).offset((page - 1) * size)

        rows = s.execute(stmt).mappings().all()
        out = []
        for r in rows:
            requester_ids = s.execute(
                select(UserRequest.user_id)
                .where(UserRequest.song_id == r["id"])
                .distinct()
            ).scalars().all()
            out.append(
                {
                    "id": r["id"],
                    "name": r["name"],
                    "artist": r["artist"],
                    "is_banned": bool(r["is_banned"]),
                    "selected": bool(r["selected"]),
                    "req_count": r["req_count"],
                    "last_time": r["last_time"],
                    "requesters": list(requester_ids),
                }
            )
        return {"data": out, "total": total, "page": page, "size": size}


@app.get("/api/songs/{sid}/requests", **_auth)
def get_song_requests(sid: int):
    with _session() as s:
        rows = s.execute(
            select(
                UserRequest.user_id,
                UserRequest.time,
                UserRequest.remark,
                UserRequest.day_count,
                Song.name,
                Song.artist,
            )
            .join(Song, Song.id == UserRequest.song_id)
            .where(UserRequest.song_id == sid)
            .order_by(UserRequest.time.desc())
        ).mappings().all()
        return {"data": [dict(r) for r in rows]}


class SelectManyIn(BaseModel):
    ids: list[int]
    note: str = ""


@app.post("/api/songs/select_many", **_auth)
def select_many(body: SelectManyIn):
    now = datetime.now().isoformat(timespec="seconds")
    with _session() as s:
        songs = s.execute(
            select(Song).where(Song.id.in_(body.ids))
        ).scalars().all()
        for song in songs:
            song.selected = True
            _record_selected_notice(s, song.id, song.name, song.artist)
            s.add(
                PlayHistory(
                    song_id=song.id,
                    user_id="",
                    note=body.note,
                    played_at=now,
                    created_at=now,
                )
            )
        s.commit()
        return {"ok": True, "count": len(songs)}


class SelectIn(BaseModel):
    user_id: str = ""
    note: str = ""


@app.post("/api/songs/{sid}/select", **_auth)
def select_song(sid: int, body: SelectIn):
    now = datetime.now().isoformat(timespec="seconds")
    with _session() as s:
        song = s.get(Song, sid)
        if not song:
            raise HTTPException(404, "歌曲不存在")
        song.selected = True
        _record_selected_notice(s, song.id, song.name, song.artist)
        s.add(
            PlayHistory(
                song_id=sid,
                user_id=body.user_id,
                note=body.note,
                played_at=now,
                created_at=now,
            )
        )
        s.commit()
        return {"ok": True}


@app.post("/api/songs/{sid}/ban", **_auth)
def ban_song(sid: int):
    with _session() as s:
        song = s.get(Song, sid)
        if song:
            song.is_banned = True
            s.commit()
    return {"ok": True}


@app.post("/api/songs/{sid}/unban", **_auth)
def unban_song(sid: int):
    with _session() as s:
        song = s.get(Song, sid)
        if song:
            song.is_banned = False
            s.commit()
    return {"ok": True}


# ---------------------------------------------------------------- 用户 ------------------------------------------------


@app.get("/api/users", **_auth)
def get_users():
    today = datetime.now().strftime("%Y-%m-%d")
    with _session() as s:
        rows = s.execute(
            select(
                User.user_id,
                User.is_banned,
                User.created_at,
                func.coalesce(
                    func.sum(UserRequest.day_count).filter(UserRequest.day == today), 0
                ).label("today_count"),
            )
            .outerjoin(UserRequest, UserRequest.user_id == User.user_id)
            .group_by(User.user_id, User.is_banned, User.created_at)
            .order_by(User.user_id)
        ).mappings().all()
        return {
            "data": [
                {
                    "user_id": r["user_id"],
                    "is_banned": bool(r["is_banned"]),
                    "created_at": r["created_at"],
                    "today_count": int(r["today_count"] or 0),
                }
                for r in rows
            ]
        }


@app.post("/api/users/{uid}/ban", **_auth)
def ban_user(uid: str):
    with _session() as s:
        user = s.get(User, uid)
        if user:
            user.is_banned = True
        else:
            s.add(
                User(
                    user_id=uid,
                    is_banned=True,
                    created_at=datetime.now().isoformat(timespec="seconds"),
                )
            )
        s.commit()
    return {"ok": True}


@app.post("/api/users/{uid}/unban", **_auth)
def unban_user(uid: str):
    with _session() as s:
        user = s.get(User, uid)
        if user:
            user.is_banned = False
            s.commit()
    return {"ok": True}


# ---------------------------------------------------------------- 播放历史 ------------------------------------------------


@app.get("/api/history", **_auth)
def get_history(name: str = "", date: str = "", page: int = 1, size: int = 20):
    page = max(int(page), 1)
    size = min(max(int(size), 1), 200)
    with _session() as s:
        stmt = (
            select(
                PlayHistory.id,
                PlayHistory.song_id,
                Song.name,
                Song.artist,
                PlayHistory.user_id,
                PlayHistory.note,
                PlayHistory.played_at,
            )
            .join(Song, Song.id == PlayHistory.song_id)
        )
        conds = []
        if name:
            conds.append(Song.name.like(f"%{name}%"))
        if date:
            conds.append(PlayHistory.played_at.like(f"{date}%"))
        if conds:
            stmt = stmt.where(*conds)
        total = s.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        stmt = stmt.order_by(PlayHistory.played_at.desc()).limit(size).offset((page - 1) * size)
        rows = s.execute(stmt).mappings().all()
        return {
            "data": [dict(r) for r in rows],
            "total": total,
            "page": page,
            "size": size,
        }


def _reset_songs_by_history_ids(ids: list[int]) -> int:
    """删除指定播放历史后，把对应歌曲的 selected 重置为 0（回到待选用）。

    先取受影响歌曲 id（去重），再清空这些歌曲的历史记录，最后重置选中状态。
    返回被重置的歌曲数。
    """
    if not ids:
        return 0
    with _session() as s:
        song_ids = list(
            s.execute(
                select(PlayHistory.song_id)
                .where(PlayHistory.id.in_(ids))
                .distinct()
            ).scalars().all()
        )
        # 事务性写入：删历史 + 重置选中状态
        s.execute(delete(PlayHistory).where(PlayHistory.id.in_(ids)))
        if song_ids:
            # 只把受影响歌曲的“已选用”标记重置为 False（回到待选用），不删除歌曲
            s.execute(
                Song.__table__.update()
                .where(Song.id.in_(song_ids))
                .values(selected=False)
            )
        s.commit()
    return len(song_ids)


@app.delete("/api/history/{hid}", **_auth)
def delete_history_one(hid: int):
    with _session() as s:
        exists = s.get(PlayHistory, hid) is not None
    if not exists:
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
    with _session() as s:
        song_ids = list(
            s.execute(select(PlayHistory.song_id).distinct()).scalars().all()
        )
        count = s.scalar(select(func.count()).select_from(PlayHistory)) or 0
        s.execute(delete(PlayHistory))
        if song_ids:
            s.execute(
                Song.__table__.update()
                .where(Song.id.in_(song_ids))
                .values(selected=False)
            )
        s.commit()
        return {"ok": True, "count": count, "reset_songs": len(song_ids)}


# ---------------------------------------------------------------- 统计 ------------------------------------------------


@app.get("/api/stats", **_auth)
def get_stats():
    with _session() as s:
        total = s.scalar(select(func.count()).select_from(UserRequest)) or 0
        requests = s.scalar(select(func.count(func.distinct(UserRequest.song_id)))) or 0
        selected = s.scalar(select(func.count()).select_from(Song).where(Song.selected.is_(True))) or 0
        banned = s.scalar(select(func.count()).select_from(Song).where(Song.is_banned.is_(True))) or 0
        pending = s.scalar(
            select(func.count())
            .select_from(Song)
            .where(Song.selected.is_(False))
            .where(Song.is_banned.is_(False))
            .where(
                Song.id.in_(select(UserRequest.song_id).distinct())
            )
        ) or 0
        hot = [
            dict(r)
            for r in s.execute(
                select(Song.name, Song.artist, func.count(UserRequest.id).label("cnt"))
                .join(UserRequest, UserRequest.song_id == Song.id)
                .group_by(Song.id)
                .order_by(func.count(UserRequest.id).desc())
                .limit(10)
            ).mappings().all()
        ]
        trend = [
            {"day": r[0], "cnt": r[1]}
            for r in s.execute(
                select(UserRequest.day, func.count())
                .group_by(UserRequest.day)
                .order_by(UserRequest.day)
            ).all()
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
