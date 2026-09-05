# QQ 机器人（第三方 · NapCat + NoneBot2）

基于 **NapCat（协议端，登录个人 QQ 号）+ NoneBot2（Python 框架）** 的 QQ 私聊点歌机器人。

> ⚠️ 本方案登录的是**个人 QQ 号**（建议小号），有被风控/封号的风险，非腾讯官方，请自行评估。

## 目录
```
qq-bot/
├── bot.py                    # NoneBot2 入口
├── pyproject.toml            # 依赖与插件配置
├── .env / .env.example       # 驱动/端口/点歌配置 + OneBot 连接
└── plugins/qq_song/
    ├── __init__.py           # 插件：点歌/帮助/记录/剩余次数
    ├── song_core.py          # 解析与格式化
    └── storage.py            # SQLite 存储
```

## 快速开始
1. 安装依赖：
   ```powershell
   cd D:\qq-bot
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -U nonebot2[fastapi]
   pip install nonebot-adapter-onebot
   ```
2. 复制 `.env.example` 为 `.env`（端口默认 8080，已有）。
3. 启动：
   ```powershell
   python bot.py
   ```
   看到 `Succeeded to load plugin "qq_song"`、`Loaded adapters: OneBot V11`、`Uvicorn running on http://127.0.0.1:8080` 即就绪。

## 对接 NapCat
1. 安装并运行 **NapCat**（Windows：NapCatQQ）。
2. 用你的 **QQ 小号**扫码登录。
3. NapCat 网络配置里添加**反向 WebSocket**，地址填：
   `ws://127.0.0.1:8080/onebot/v11/ws`（对应 `.env` 的 `PORT=8080`）。
4. 若走**正向 WebSocket**：NapCat 开一个 WS 服务端（如 3001），`.env` 写 `ONEBOT_WS_URLS=["ws://127.0.0.1:3001"]`。

## 使用（QQ 私聊）
- 用户把机器人小号**加为好友 / 加入消息列表**，然后直接私聊。
- `点歌`（或 `/点歌`）→ 开启点歌模式，回「点歌服务已开启」。
- 点歌模式下发 `歌名-歌手`（如 `晴天-周杰伦`）→ 写入 SQLite，回「信息已录入」；格式错回「输入信息有误」。
- `帮助` → 菜单，可用 `1`/`2`/`3` 快捷键（仅打开帮助后下一条有效）。
- `查看我的点歌记录` / `查询剩余点歌次数`。
- 记录默认存于 `data/song_requests.db`（可用 `QQ_SONG_DATA_FILE` 改）。

## 说明
- 群聊里需 **@机器人** 触发（`to_me`）；私聊直接发即可。
- 不依赖 QQ 开放平台/审核/沙箱。
