# 校园广播站 · 点歌管理台（后端 + 前端）

管理后台分两部分：
- **后端**：`web-admin/backend/app.py`（纯 API，FastAPI + 异步 SQLAlchemy + asyncpg，PostgreSQL），不托管任何静态文件
- **前端**：独立 Vue3 项目 **`radio-admin`**（位于 `~/WebstormProjects/radio-admin`，Vite + TypeScript + Element Plus + Pinia），通过跨域直接访问后端 API

## 后端运行

先安装项目依赖（QQbot 项目根目录执行）：
```powershell
pip install -e .
```

配置后端（有自己的配置文件，不复用 bot 的 .env）：
```powershell
Copy-Item web-admin\backend\.env.example web-admin\backend\.env
# 编辑 web-admin\backend\.env 填入 DATABASE_URL 与（可选）筛选 agent 的 LLM 配置
```

启动后端：
```powershell
.\\.venv\\Scripts\\python.exe web-admin\\backend\\app.py
```
默认监听 `http://127.0.0.1:8600`（`WEB_ADMIN_PORT`）。部署到 api.example.com 之类域名时，
把 `WEB_ADMIN_CORS` 收紧为前端域名。

## 前端运行（radio-admin）

```bash
cd ~/WebstormProjects/radio-admin
pnpm install
pnpm dev          # 开发模式：/api 代理到 http://127.0.0.1:8600
pnpm build        # 构建产物在 dist/，部署到任意静态托管
```

前端访问后端地址由 `VITE_API_BASE` 指定（复制 `.env.example` 为 `.env.production` 后填写）：
```env
# 留空 = 同源（开发走 vite 代理）；部署时填真实地址
VITE_API_BASE=https://api.example.com
```

## 鉴权

在 `web-admin/backend/.env` 设置 `WEB_ADMIN_USERNAME` / `WEB_ADMIN_PASSWORD` 后，
需先 `POST /api/login` 拿 token；两者都不设置则不鉴权（仅本地调试）。
所有管理接口统一 `Authorization: Bearer <token>`。

## 接口速览

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/login` | 登录拿 token |
| GET | `/api/pool` | 点歌池（含点歌人列表） |
| GET | `/api/songs/{id}/requests` | 某首歌的点歌记录 |
| POST | `/api/songs/select_many` / `/api/songs/{id}/select` | 选用（记入历史 + 通知缓存） |
| POST | `/api/songs/{id}/ban` / `unban` | 禁播 / 解禁 |
| POST | `/api/songs/ban_many` | 批量禁播 |
| GET | `/api/users` | 用户列表 |
| POST | `/api/users/{uid}/ban` / `unban` | 封禁 / 解封 |
| GET/DELETE/POST | `/api/history…` | 播放历史查询 / 删除 |
| GET | `/api/stats` | 统计 |
| GET/PUT | `/api/permissions` | 权限白名单 |
| GET | `/api/notices/status` | 选中通知状态（待发送/已发送/失败） |
| POST | `/api/pool/candidates` | 每日选曲向导：按条件返回候选总数与点歌人列表 |
| POST | `/api/pool/draw` | 每日选曲向导：按条件（加权）随机抽取歌曲（含音频/网页链接） |
| GET | `/api/agent/rules` | 筛选 agent 的禁播判定规则文本 |
| POST | `/api/agent/screen-songs` | 逐首 LLM 判定歌曲（安全/可疑/禁播 + 理由，带 24h 缓存） |

前端对接层在 radio-admin 项目的 `src/api/index.ts`。
