# QQ 点歌机器人（第三方 · NapCat + NoneBot2）

基于 **NapCat（协议端，登录个人 QQ 号）+ NoneBot2（Python 框架）** 的 QQ 私聊/群聊点歌机器人。成员通过**私聊机器人**发送「歌名-歌手」即可点歌，机器人会记录到 SQLite 并回复。

> ⚠️ 本方案登录的是**个人 QQ 号**（建议小号），有被风控/封号风险，非腾讯官方，请自行评估。

## 功能
- **点歌**：发 `点歌` 开启点歌模式，再发 `歌名-歌手`（如 `晴天-周杰伦`）→ 写入 SQLite，回复「信息已录入」；格式错回复「输入信息有误」。
- **帮助**：发 `帮助`/`菜单` 显示菜单；随后可用 `1`/`2`/`3` 快捷键（仅打开帮助后的下一条消息有效）。
- **查看我的点歌记录**：列出你点过的歌（最近在前）。
- **查询剩余点歌次数**：返回「今天已点 X/上限 首，剩余 N 首」（每用户每日上限 `QQ_SONG_DAILY_LIMIT`，默认 5）。
- 群聊里需 **@机器人** 触发（`to_me`）；私聊直接发即可。

## 目录结构
```
qq-bot/
├── bot.py                    # NoneBot2 入口
├── pyproject.toml            # 依赖与插件配置
├── start.bat                 # 一键启动（NapCat + 机器人）
├── .env / .env.example       # 驱动/端口/点歌配置 + OneBot 连接
├── plugins/qq_song/
│   ├── __init__.py           # 插件：点歌/帮助/记录/剩余次数
│   ├── song_core.py          # 解析与格式化
│   └── storage.py            # SQLite 存储
└── README.md
```

## 快速开始（本机）
1. 安装依赖：
   ```powershell
   cd D:\qq-bot
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -U "nonebot2[fastapi]" nonebot-adapter-onebot
   ```
2. 配置：`Copy-Item .env.example .env`（端口默认 8080）。
3. 安装并登录 **NapCat**（不在仓库内），在 NapCat 里配置**反向 WebSocket**：
   ```
   ws://127.0.0.1:8080/onebot/v11/ws
   ```
4. 启动机器人：
   ```powershell
   .\.venv\Scripts\python.exe bot.py
   ```
   看到 `Succeeded to load plugin "qq_song"`、`Uvicorn running on http://127.0.0.1:8080` 即就绪。
5. 也可用 `start.bat` 一键启动（NapCat + 机器人）。首次运行需以小号扫码登录。
6. 用**另一个账号**把机器人小号加为好友并私聊：`点歌` → `晴天-周杰伦`。

## 从 GitHub 部署到另一台电脑
1. 安装 Git 并克隆：
   ```powershell
   git clone https://github.com/SDotm1114/QQbot.git
   cd QQbot
   ```
2. 安装 Python（3.9+）并建虚拟环境装依赖：
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -U "nonebot2[fastapi]" nonebot-adapter-onebot
   ```
3. 配置环境：`Copy-Item .env.example .env`
4. 安装并登录 NapCat（需单独下载），配置反向 WebSocket：`ws://127.0.0.1:8080/onebot/v11/ws`
5. 启动：`.\.venv\Scripts\python.exe bot.py`；或 `start.bat`。

## 配置项
| 变量 | 说明 | 默认 |
|---|---|---|
| `DRIVER` | NoneBot 驱动器 | `~fastapi` |
| `HOST` / `PORT` | 监听地址/端口（NapCat 反向 WS 指向它） | `127.0.0.1` / `8080` |
| `QQ_SONG_DATA_FILE` | 点歌记录数据库文件 | `data/song_requests.db` |
| `QQ_SONG_DAILY_LIMIT` | 每用户每日点歌上限 | `5` |
| `QQ_SONG_RECORD_LIMIT` | 查看记录最多展示条数 | `20` |

## 说明
- 记录存储：SQLite，默认 `data/song_requests.db`（可用 `QQ_SONG_DATA_FILE` 改）。
- 不依赖 QQ 开放平台/审核/沙箱；登录的是个人 QQ 小号。
- NapCat、`.venv`、`.env`、`data` 均不入库（已在 `.gitignore` 排除）。
