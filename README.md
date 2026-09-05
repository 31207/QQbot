# QQ 点歌机器人（第三方 · NapCat + NoneBot2）

基于 **NapCat（协议端，登录个人 QQ 号）+ NoneBot2（Python 框架）** 的 QQ 音乐机器人：成员在**私聊机器人**时搜索歌曲、点歌，机器人把结果绘制成图片返回，点歌记录存入 SQLite。

> ⚠️ 本方案登录的是**个人 QQ 号**（建议小号），有被风控/封号风险，非腾讯官方，请自行评估。
>
> 音乐搜索依赖自建的 **Go Music API**（跨平台音乐搜索/解析服务），需另行部署并配置 `QQ_MUSIC_API_BASE`。

## 功能
- **音乐搜索**：发 `搜索 歌名`（可加平台前缀如 `搜索 qq 晴天`）多平台搜索，结果以图片返回（每页 10 条），`上一页`/`下一页` 翻页。
- **点歌**：发 `点歌 序号` 点选最近一次搜索结果中的歌曲；每日有上限，重复点歌会把该歌置顶歌单且当日次数照扣。
- **我的歌单**：发 `我的歌单`/`歌单` 查看点歌记录图片（含封面、歌手、来源、时间、歌曲编号、备注）。
- **备注**：发 `备注 编号 内容` 给已点歌曲加备注，`备注 编号` 清除备注。
- **查询剩余点歌次数**：返回「今天已点 X/上限 首」。
- **管理命令**：`封禁 用户ID` / `解封 用户ID` / `封禁列表`（仅超级管理员 `SUPERUSERS`）；被封禁用户无法使用点歌功能。
- 所有指令**仅私聊**可用（私聊直接发，无需 @）。

## 系统架构

<p align="center"><img src="docs/structure.svg" width="100%" alt="项目结构与数据库设计"/></p>

## 指令与流程

<p align="center"><img src="docs/flows.svg" width="100%" alt="指令与流程"/></p>

## 目录结构
```
qq-bot/
├── bot.py                    # NoneBot2 入口
├── pyproject.toml            # 依赖与插件配置
├── start.bat                 # 一键启动（NapCat + 机器人）
├── .env / .env.prod          # 驱动/端口/插件配置
├── plugins/
│   ├── qq_music_search/      # 音乐搜索插件（api/covers/render）
│   └── qq_song/              # 点歌插件（点歌/歌单/备注/存储）
├── data/
│   ├── song_requests.db      # SQLite 数据库
│   └── covers/               # 封面缓存
└── docs/                     # 架构与流程图
```

## 快速开始（本机）
1. 安装依赖：
   ```powershell
   cd D:\qq-bot
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -U "nonebot2[fastapi,websockets]" nonebot-adapter-onebot httpx pillow
   ```
2. 部署 **Go Music API**（另行搭建），并在 `.env` 中把 `QQ_MUSIC_API_BASE` 指向它。
3. 配置：`Copy-Item .env.example .env`。
4. 安装并登录 **NapCat**（不在仓库内），在 NapCat 里配置**反向 WebSocket**：
   ```
   ws://127.0.0.1:8080/onebot/v11/ws
   ```
   也可以正向 WebSocket：`.env` 中设置 `ONEBOT_WS_URLS` 指向 NapCat 的 WS 服务端。
5. 启动机器人：
   ```powershell
   .\.venv\Scripts\python.exe bot.py
   ```
   看到 `Succeeded to load plugin "qq_music_search"`、`Succeeded to load plugin "qq_song"` 即就绪。
6. 用**另一个账号**把机器人小号加为好友并私聊：`搜索 晴天` → `点歌 1`。

## 从 GitHub 部署到另一台电脑
1. 克隆并进入项目：`git clone https://github.com/SDotm1114/QQbot.git`。
2. 安装 Python（3.9+），建虚拟环境并按上方命令安装依赖。
3. 配置环境：`Copy-Item .env.example .env`，设置 `QQ_MUSIC_API_BASE` 等配置项。
4. 部署 Go Music API 与 NapCat（均需单独准备），NapCat 配置反向 WebSocket。
5. 启动：`.\.venv\Scripts\python.exe bot.py`；或 `start.bat`。

## 配置项
| 变量 | 说明 | 默认 |
|---|---|---|
| `DRIVER` | NoneBot 驱动器（fastapi 反代 WS + websockets 正向 WS 客户端） | `~fastapi+~websockets` |
| `HOST` / `PORT` | 监听地址/端口（NapCat 反向 WS 指向它） | `127.0.0.1` / `8080` |
| `ONEBOT_WS_URLS` | 正向 WebSocket 地址（NapCat 作为 WS 服务端时） | 空 |
| `QQ_MUSIC_API_BASE` | Go Music API 地址 | `http://127.0.0.1:8080` |
| `QQ_MUSIC_COVER_DIR` | 封面缓存目录 | `data/covers` |
| `QQ_MUSIC_PAGE_SIZE` | 搜索每页条数 | `10` |
| `QQ_MUSIC_SESSION_TTL` | 搜索会话有效期（秒） | `600` |
| `QQ_SONG_DATA_FILE` | 点歌数据库文件 | `data/song_requests.db` |
| `QQ_SONG_DAILY_LIMIT` | 每用户每日点歌上限 | `5` |
| `QQ_SONG_RECORD_LIMIT` | 歌单最多展示条数 | `20` |
| `SUPERUSERS` | 超级管理员 QQ 号（管理命令权限），JSON 数组 | `[]` |

## 说明
- 记录存储：SQLite，默认 `data/song_requests.db`（歌曲库 `songs`、用户 `users`、点歌记录 `user_requests` 三表）。
- 封面统一经 Go Music API 的 `/api/v1/music/cover` 代理下载并缓存到 `data/covers/`（按 URL 的 md5 命名）。
- 不依赖 QQ 开放平台/审核/沙箱；登录的是个人 QQ 小号。
- NapCat、`.venv`、`.env`、`data` 均不入库（已在 `.gitignore` 排除）。
