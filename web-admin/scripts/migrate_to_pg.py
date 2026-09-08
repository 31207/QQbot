"""把本地 SQLite 真实数据（data/song_requests.db）迁移到 PostgreSQL。

用法（项目根目录运行）：
    $env:DATABASE_URL="postgresql+psycopg://user:pass@host:port/db"
    .\\.venv\\Scripts\\python.exe web-admin\\scripts\\migrate_to_pg.py

说明：
- 只读取 SQLite（只读打开），不修改任何源文件。
- 迁移 4 张在用表：songs / users / user_requests / play_history，含保留原 id 与索引。
- 历史遗留的 song_requests 表（无代码使用）不迁移。
- PG 侧会先清空这 4 张表再写入，可重复执行。
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # 项目根，供 import db

from sqlalchemy import delete, text

from db import PlayHistory, SessionLocal, Song, User, UserRequest

_ROOT = Path(__file__).resolve().parent.parent.parent  # qq-bot/
_SQLITE = Path(os.environ.get("SQLITE_SRC") or (_ROOT / "data" / "song_requests.db"))


def _load_sqlite_rows(db_path: Path):
    """只读加载 SQLite 各表为 dict 列表，保留原始 id。"""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    out = {}
    for t in ("songs", "users", "user_requests", "play_history"):
        rows = con.execute(f"SELECT * FROM {t}").fetchall()
        out[t] = [dict(r) for r in rows]
    con.close()
    return out


def main() -> None:
    if not _SQLITE.exists():
        raise SystemExit(f"未找到 SQLite 源库：{_SQLITE}")
    if not DATABASE_URL.startswith("postgresql"):
        raise SystemExit("请先设置 DATABASE_URL 指向 PostgreSQL（postgresql+psycopg://...）")

    data = _load_sqlite_rows(_SQLITE)
    print(f"源库 {_SQLITE.name} 读取结果：")
    for t, rows in data.items():
        print(f"  {t}: {len(rows)} 行")

    with SessionLocal() as s:
        # 清空目标表（顺序：先清子表再清主表，避免外键约束）
        s.execute(delete(PlayHistory))
        s.execute(delete(UserRequest))
        s.execute(delete(User))
        s.execute(delete(Song))
        s.commit()

        # 主表先写入并落库，再写子表，保证外键 sid 已存在
        for r in data["songs"]:
            s.merge(
                Song(
                    id=r["id"],
                    source=r.get("source") or "",
                    source_id=r.get("source_id") or "",
                    name=r.get("name") or "",
                    artist=r.get("artist") or "",
                    album=r.get("album") or "",
                    cover=r.get("cover") or "",
                    duration=int(r.get("duration") or 0),
                    url=r.get("url") or "",
                    link=r.get("link") or "",
                    is_banned=bool(r.get("is_banned")),
                    play_count=int(r.get("play_count") or 0),
                    created_at=r.get("created_at") or "",
                    selected=bool(r.get("selected")),
                )
            )
        s.commit()  # songs 落库

        for r in data["users"]:
            s.merge(
                User(
                    user_id=r["user_id"],
                    is_banned=bool(r.get("is_banned")),
                    created_at=r.get("created_at") or "",
                )
            )
        s.commit()  # users 落库

        for r in data["user_requests"]:
            s.merge(
                UserRequest(
                    id=r["id"],
                    user_id=r["user_id"],
                    song_id=r["song_id"],
                    time=r.get("time") or "",
                    remark=r.get("remark") or "",
                    day=r.get("day") or "",
                    day_count=int(r.get("day_count") or 0),
                )
            )
        s.commit()  # user_requests 落库

        for r in data["play_history"]:
            s.merge(
                PlayHistory(
                    id=r["id"],
                    song_id=r["song_id"],
                    user_id=r.get("user_id") or "",
                    note=r.get("note") or "",
                    played_at=r.get("played_at") or "",
                    created_at=r.get("created_at") or "",
                )
            )
        s.commit()  # play_history 落库

    # 汇总验证
    from sqlalchemy import func, select

    with SessionLocal() as s:
        counts = {
            "songs": s.scalar(select(func.count()).select_from(Song)),
            "users": s.scalar(select(func.count()).select_from(User)),
            "user_requests": s.scalar(select(func.count()).select_from(UserRequest)),
            "play_history": s.scalar(select(func.count()).select_from(PlayHistory)),
        }
        # PG 显式写入 id 后，把自增序列同步到 max(id)+1，避免新插入的主键冲突
        for tbl in ("songs", "user_requests", "play_history"):
            s.execute(text(
                f"SELECT setval(pg_get_serial_sequence('{tbl}', 'id'), "
                f"COALESCE((SELECT MAX(id) FROM {tbl}), 0) + 1, false)"
            ))
        s.commit()
    print("迁移完成，PG 目标库（当前库）：")
    for t, n in counts.items():
        print(f"  {t}: {n} 行")


if __name__ == "__main__":
    from db import DATABASE_URL  # noqa: W0611  仅用于启动时的校验

    main()
