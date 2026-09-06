"""从真实库生成脱敏范例库：web-admin/sample_db/song_requests.db。

- 所有用户 QQ 号 → 88888888
- 时间戳 → 2026-01-01T00:00:00（day → 2026-01-01）
- 歌曲信息保留

用法：在项目根目录运行
    .\\.venv\\Scripts\\python.exe web-admin\\scripts\\make_sample_db.py
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent  # qq-bot/
REAL = ROOT / "data" / "song_requests.db"
SAMPLE_DIR = ROOT / "web-admin" / "sample_db"
SAMPLE = SAMPLE_DIR / "song_requests.db"

TS = "2026-01-01T00:00:00"
DAY = "2026-01-01"
MASTER_UID = "88888888"


def main() -> None:
    if not REAL.exists():
        raise SystemExit(f"未找到真实库：{REAL}")
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy(REAL, SAMPLE)

    con = sqlite3.connect(str(SAMPLE))
    cur = con.cursor()

    # users：合并成单一用户
    cur.execute("DELETE FROM users")
    cur.execute(
        "INSERT INTO users (user_id, is_banned, created_at) VALUES (?, 0, ?)",
        (MASTER_UID, TS),
    )

    # user_requests：按歌曲去重，都归到 88888888
    rows = cur.execute(
        "SELECT song_id, remark, day_count FROM user_requests"
    ).fetchall()
    cur.execute("DELETE FROM user_requests")
    seen: set[int] = set()
    for song_id, remark, day_count in rows:
        if song_id in seen:
            continue
        seen.add(song_id)
        cur.execute(
            "INSERT INTO user_requests "
            "(user_id, song_id, time, remark, day, day_count) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (MASTER_UID, song_id, TS, remark or "", DAY, int(day_count or 0)),
        )

    # songs：保留信息，重置禁播/选用
    cur.execute("UPDATE songs SET is_banned = 0, selected = 0")

    # play_history：清空并放几条示例
    cur.execute("DELETE FROM play_history")
    song_ids = [r[0] for r in cur.execute("SELECT id FROM songs").fetchall()]
    for i, sid in enumerate(song_ids[:3]):
        cur.execute(
            "INSERT INTO play_history "
            "(song_id, user_id, note, played_at, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (sid, MASTER_UID, f"示例选用 #{i + 1}", TS, TS),
        )

    con.commit()
    con.close()
    print(f"已生成脱敏范例库：{SAMPLE}")
    print(f"  用户数=1（{MASTER_UID}）  点歌记录={len(seen)} 条  播放历史=3 条")


if __name__ == "__main__":
    main()
