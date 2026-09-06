# 校园广播站 · 点歌管理台（Web 前端 + 本地数据接口）

本地运行的 Vue3 + Element Plus（CDN，无需 Node 构建）管理后台，后端 FastAPI 直读
`data/song_requests.db`（含迁移：`songs.selected`、`play_history` 表）。

## 运行

在项目根目录执行：
```powershell
.\.venv\Scripts\python.exe web-admin\backend\app.py
```

浏览器打开：**http://127.0.0.1:8600**

## 当前功能

- **点歌池**：所有被点过的歌（歌名/歌手/点歌人/次数/最近点歌/状态）。
  - **选用**：标记歌曲已选用，并记入播放历史（可填备注）。
  - **禁播 / 解禁**：`UPDATE songs.is_banned`。
- **播放历史**：选用即写入 `play_history`，可查看时间/歌曲/点歌人/备注。
- 顶部统计：累计点歌、被点歌曲数、待选用、已禁播。

## 预留接口（后续接到云端 fastapi 用）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/pool` | 点歌池 |
| GET | `/api/history` | 播放历史 |
| GET | `/api/stats` | 统计 |
| POST | `/api/songs/{id}/select` | 选用（记入播放历史），body `{user_id?, note?}` |
| POST | `/api/songs/{id}/ban` | 禁播 |
| POST | `/api/songs/{id}/unban` | 解禁 |

`frontend/index.html` 里的 `api.get / api.post` 就是对接层，后端已在本地实现同名接口。
