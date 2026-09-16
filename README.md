# QQ 点歌机器人（第三方 · NapCat + NoneBot2）

基于 **NapCat（协议端，登录个人 QQ 号）+ NoneBot2（Python 框架）** 的 QQ 音乐机器人，同时**可选接入官方 QQ 机器人（nonebot-adapter-qq，双适配器并存）**：成员在**私聊机器人**时搜索歌曲、点歌，机器人把结果绘制成图片返回，点歌记录存入 PostgreSQL。

> ⚠️ 本方案登录的是**个人 QQ 号**（建议小号），有被风控/封号风险，非腾讯官方，请自行评估。
>
> 音乐搜索依赖自建的 **Go Music API**（跨平台音乐搜索/解析服务），需另行部署并配置 `QQ_MUSIC_API_BASE`。

## 功能
- **音乐搜索**：发 `搜索 歌名`（可加平台前缀如 `搜索 qq 晴天`）多平台搜索，结果以图片返回（每页 10 条），`上一页`/`下一页` 翻页。
- **点歌**：发 `点歌 序号` 点选最近一次搜索结果中的歌曲；每周有上限（管理员每日），重复点歌会把该歌置顶歌单且次数照扣。
- **分享点歌（推荐）**：直接把 QQ 音乐/网易云等**歌曲分享卡片**发给机器人，自动转为精确搜索词并返回**结果图**，确认后即可点歌。
- **加好友欢迎**：成为好友后自动发送**欢迎词 + 功能清单**（重点提示可直接分享点歌）。
- **我的歌单**：发 `我的歌单`/`歌单` 查看点歌记录图片（含封面、歌手、来源、时间、歌曲编号、备注）。
- **备注**：发 `备注 编号 内容` 给已点歌曲加备注，`备注 编号` 清除备注。
- **查询剩余点歌次数**：返回「今天已点 X/上限 首」。
- **管理命令**：`封禁 用户ID` / `解封 用户ID` / `封禁列表`（仅超级管理员）；被封禁用户无法使用点歌功能。
- **通知管理（管理员）**：`通知状态` 查看选中通知的发送情况（待发送/已发送/失败）；`发送通知` 立即手动发送所有待处理通知（定时为每周五 19:00 自动发送）。
- **AI 智能助手（可选，默认关闭）**：对接任意 OpenAI 兼容大模型（DeepSeek / 智谱 GLM / 通义千问 / Kimi）。开启后：确定性指令（搜索/点歌/…）**照常本地处理**，LLM 仅做回复措辞；自然语言消息由大模型函数调用理解。LLM 故障不影响确定性指令。
- **权限分级（三级）**：用户、管理员、超级管理员。管理员额外可**重置所有人点歌次数**、**禁播/解禁歌曲**；超级管理员额外可**封禁/解封用户**。权限只能通过 `data/permissions.json` 白名单文件授予，机器人端无法授予。
- 所有指令**仅私聊**可用（私聊直接发，无需 @）。
- **双适配器**：OneBot V11（NapCat）与官方 QQ（开放平台机器人）可同时接入；业务逻辑共用，收发按适配器自动适配（官方 QQ 发图自动走文件上传 API）。官方机器人的用户标识是 **user_openid**（非 QQ 号），封禁/白名单需按 openid 配置；歌曲分享卡片链路仅 NapCat 支持。

## 架构

- 分层：**插件层**（消息路由/状态流转）→ **动作层**（功能实现，指令与 LLM 工具共用一份）→ **服务层**（业务/持久化，纯业务无 adapter 依赖）→ **db 层**（异步 SQLAlchemy）。
- 单插件单入口：`src/qqbot/plugins/qq_music_bot` 一个 matcher 统一分发，无插件间隐式依赖、无优先级数字耦合。
- 异步数据库：PostgreSQL（asyncpg），bot 与 web-admin 共用同一连接串 `DATABASE_URL`，点歌写入用单条 `INSERT … ON CONFLICT` 原子完成，无读改写竞态。
- 无内存泄漏：所有进程内状态（搜索会话/LLM 记忆/一次性模式）带 TTL，由后台维护任务定期回收；点歌写入用单条 `INSERT … ON CONFLICT` 原子完成，无读改写竞态。

```
qq-bot/
├── bot.py                        # NoneBot2 入口
├── pyproject.toml                # 依赖 + nonebot 插件配置（src 布局）
├── .env / .env.prod              # 驱动/端口/插件配置
├── src/qqbot/
│   ├── config.py                 # 统一配置（唯一解析点）
│   ├── state.py                  # 进程内会话状态（TTL 自动回收）
│   ├── render.py                 # Pillow 图片渲染
│   ├── db/                       # 异步引擎/会话/模型/原子 UPSERT
│   ├── services/                 # 业务服务（点歌/搜索/用户/权限/封面/通知/LLM）
│   └── plugins/qq_music_bot/     # NoneBot 插件（分发/指令解析/动作层/分享解析）
├── web-admin/
│   ├── backend/app.py            # FastAPI 管理台接口（异步，共用 qqbot 包）
│   └── frontend/index.html       # Vue3 + Element Plus（CDN，锁定版本）
├── tests/                        # pytest + pytest-asyncio
└── docs/                         # 架构与流程图
```

## 快速开始（本机）

1. 安装依赖（**editable 安装项目本身**，让 `import qqbot` 在 bot / web-admin / 测试里都可用）：
   ```powershell
   cd D:\qq-bot
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -e ".[dev]"
   ```
2. 准备 **PostgreSQL**（15+），建好库与账号，例如：
   ```sql
   CREATE ROLE qqbot LOGIN PASSWORD '你的密码';
   CREATE DATABASE qqbot OWNER qqbot;
   ```
3. 配置：`Copy-Item .env.example .env`，把 `DATABASE_URL` 填成 `postgresql+asyncpg://qqbot:你的密码@127.0.0.1:5432/qqbot`。
4. 部署 **Go Music API**（另行搭建），并在 `.env` 中把 `QQ_MUSIC_API_BASE` 指向它。
5. 安装并登录 **NapCat**（不在仓库内），在 NapCat 里配置**反向 WebSocket**：
   ```
   ws://127.0.0.1:8080/onebot/v11/ws
   ```
   也可以正向 WebSocket：`.env` 中设置 `ONEBOT_WS_URLS` 指向 NapCat 的 WS 服务端。
6. 启动机器人：
   ```powershell
   .\.venv\Scripts\python.exe bot.py
   ```
   看到 `Succeeded to load plugin "qq_music_bot"` 即就绪。
7. 用**另一个账号**把机器人小号加为好友并私聊：`搜索 晴天` → `点歌 1`。

### 启动管理台
管理台前端是独立的 Vue3 项目（`~/WebstormProjects/radio-admin`，见 web-admin/README.md），跨域直连后端。
后端是纯 API 服务，有自己的配置文件 `web-admin/backend/.env`（复制 `.env.example` 填写 DATABASE_URL 与筛选 agent 的 LLM 配置）：
```powershell
Copy-Item web-admin\backend\.env.example web-admin\backend\.env
.\.venv\Scripts\python.exe web-admin\backend\app.py
```
后端默认监听 **http://127.0.0.1:8600**（端口 `WEB_ADMIN_PORT`）。

### 运行测试
测试连本地 PostgreSQL（默认库 `qqbot_test`、用户 `qqbot_admin`），密码经 `PGPASSWORD` 提供，也可用 `TEST_DATABASE_URL` 指定连接串：
```powershell
$env:PGPASSWORD="你的密码"
pytest -q
```

## 配置项
| 变量 | 说明 | 默认 |
|---|---|---|
| `DRIVER` | NoneBot 驱动器（fastapi 反代 WS + websockets 正向 WS 客户端） | `~fastapi+~websockets` |
| `HOST` / `PORT` | 监听地址/端口（NapCat 反向 WS 指向它） | `127.0.0.1` / `8080` |
| `ONEBOT_WS_URLS` | 正向 WebSocket 地址（NapCat 作为 WS 服务端时） | 空 |
| `QQ_BOTS` | 官方 QQ 机器人配置（JSON 数组：`[{"id","token","secret"}]`），留空则不接官方 QQ | 空 |
| `DATABASE_URL` | PostgreSQL 连接串（**必填**），如 `postgresql+asyncpg://user:pass@127.0.0.1:5432/qqbot` | 无 |
| `QQ_MUSIC_API_BASE` | Go Music API 地址 | `http://127.0.0.1:8081` |
| `QQ_MUSIC_COVER_DIR` | 封面缓存目录 | `data/covers` |
| `QQ_MUSIC_PAGE_SIZE` | 搜索每页条数 | `10` |
| `QQ_MUSIC_SESSION_TTL` | 搜索会话有效期（秒） | `600` |
| `QQ_SONG_WEEK_LIMIT` | 每用户每周点歌上限 | `5` |
| `QQ_SONG_ADMIN_DAILY_LIMIT` | 管理员及以上每日点歌上限 | `99` |
| `QQ_SONG_RECORD_LIMIT` | 歌单最多展示条数 | `20` |
| `QQ_SONG_NOTIFY_INTERVAL` | 歌曲选中通知检测 DB 间隔（秒） | `86400` |
| `QQ_SONG_NOTIFY_WEEKDAY` | 每周发送通知的星期（0=周一…4=周五） | `4` |
| `QQ_SONG_NOTIFY_HOUR` | 每周发送通知的时 | `19` |
| `QQ_SONG_NOTIFY_MINUTE` | 每周发送通知的分 | `0` |
| `LLM_ENABLED` | 是否开启 LLM 智能助手（`true`/`false`） | `false` |
| `LLM_API_BASE` | LLM 接口地址（OpenAI 兼容） | 空 |
| `LLM_API_KEY` | LLM API Key | 空 |
| `LLM_MODEL` | 模型名（如 `deepseek-chat`） | `deepseek-chat` |
| `LLM_TIMEOUT` | LLM 请求超时（秒） | `30` |
| `LLM_MEMORY_TTL` | 多轮记忆保留时长（秒） | `1800` |
| `LLM_MEMORY_TURNS` | 记忆最多保留的消息条数 | `12` |
| `LLM_MAX_STEPS` | 单次对话最大函数调用步数 | `4` |
| `QQ_PERMISSIONS_FILE` | 权限白名单文件路径 | `data/permissions.json` |

> Web 管理台使用自己的配置文件 `web-admin/backend/.env`（不读 bot 的 .env）：`DATABASE_URL`、`WEB_ADMIN_USERNAME/PASSWORD`、`WEB_ADMIN_PORT`、`WEB_ADMIN_CORS`。

## LLM 智能助手（可选）
开启后消息处理顺序：
1. 歌曲分享卡片 → LLM 转精确搜索词 → 结果图 → 确认点歌；
2. 管理指令 → 本地校验权限执行；
3. 确定性指令（`搜索` / `点歌` / `我的歌单` / `剩余次数` / `备注` / `帮助` / `上一页` / `下一页`）→ 本地执行，LLM 用「咪」的傲娇口吻措辞（失败自动回退原文）；
4. 其余自然语言 → LLM 函数调用理解并回复（工具复用同一套动作实现，支持多轮记忆）。

未配置 `LLM_ENABLED=true` 及接口信息时，插件不接管自然语言，机器人按确定性指令工作。
回复是傲娇小猫「咪」的口吻，自动避免工具结果与大模型回复重复。

示例配置：
```env
LLM_ENABLED=true
LLM_API_BASE=https://api.deepseek.com/v1
LLM_API_KEY=sk-xxxx
LLM_MODEL=deepseek-chat
```

## 权限分级（白名单）
三级权限：**用户 > 管理员 > 超级管理员**。白名单只读自文件，**机器人端无法授予权限**。

`data/permissions.json`（默认路径，可用 `QQ_PERMISSIONS_FILE` 修改）：
```json
{
  "admins": ["管理员QQ号"],
  "super_admins": ["超级管理员QQ号"]
}
```
- **用户**：可使用搜索、点歌、我的歌单、剩余次数、备注、帮助。
- **管理员**：上述全部 + `重置点歌次数`、`禁歌 歌名/编号`、`解禁歌 歌名/编号`、`通知状态`、`发送通知`。
- **超级管理员**：管理员全部 + `封禁 用户ID`、`解封 用户ID`、`封禁列表`。

修改该文件后无需重启（按文件更新时间自动重载）。被封禁用户无法使用点歌功能。

## 说明
- 记录存储：PostgreSQL（`DATABASE_URL` 必配，bot 与 web 共用同一库）。
- 封面统一经 Go Music API 的 `/api/v1/music/cover` 代理下载并缓存到 `data/covers/`（按 URL 的 md5 命名）。
- 不依赖 QQ 开放平台/审核/沙箱；登录的是个人 QQ 小号。
- NapCat、`.venv`、`.env`、`data` 均不入库（已在 `.gitignore` 排除）。
- CI：`.github/workflows/ci.yml`，Python 3.10 / 3.12 跑 pytest。
