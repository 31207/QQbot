# 部署 repo 部分到 Linux 服务器（bot + web）

本文覆盖“GitHub 仓库里的可部署代码”：`bot.py`（NoneBot2 点歌机器人）与
`web-admin/`（FastAPI 管理台 + Vue3 前端）。两者共用 `db.py` 里的
`DATABASE_URL`，因此 **PostgreSQL 必须先就绪**。

前置（已完成）：go-music-api 在 `:8081`、nginx 已初始化。
本文补齐：PostgreSQL → 拉代码 → 装依赖 → 配置 `.env` → systemd 常驻 → nginx 站点。
NapCat 不在本仓库内，单独一节说明。

## 0. 目录与用户约定

- 代码根目录：`/opt/QQbot`，属主为系统用户 `qqbot`。
- 配置：`/opt/QQbot/.env`（严格 `chmod 600`，勿入库）。
- 封面等数据写 `/opt/QQbot/data/`。

## 1. 装系统依赖

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git postgresql postgresql-contrib
```

## 2. 创建运行用户

```bash
sudo useradd --system --home /opt/QQbot --shell /usr/sbin/nologin qqbot
sudo mkdir -p /opt/QQbot
sudo chown -R qqbot:qqbot /opt/QQbot
```

> 若本机已有同名普通用户，可跳过 useradd，直接设置目录属主。

## 3. PostgreSQL

```bash
sudo systemctl enable --now postgresql
sudo -u postgres psql -c "CREATE USER qqbot WITH PASSWORD 'CHANGE_ME';"
sudo -u postgres psql -c "CREATE DATABASE qqbot OWNER qqbot;"
```

确认 `127.0.0.1` 走密码认证并允许连接：

```bash
# 查看,若为 peer 或未包含 127.0.0.1,请把对应行改为 scram-sha-256
sudo grep -n "127.0.0.1" /etc/postgresql/*/main/pg_hba.conf
sudo systemctl restart postgresql
```

数据迁移（可选，把本地真实数据带过去）：

```bash
# 本地导出
pg_dump -h 127.0.0.1 -p 5433 -U qqbot -Fc qqbot_test > qqbot.dump
# 服务器恢复（上传 qqbot.dump 后）
pg_restore -h 127.0.0.1 -U qqbot -d qqbot --clean --if-exists qqbot.dump
```

不迁就空库起步：`db.py` 的 `init_db()` 会在 bot/web 首次启动时自动建表。

## 4. 拉代码

```bash
sudo -u qqbot bash -lc 'cd /opt/QQbot && git clone https://github.com/SDotm1114/QQbot.git .'
```

## 5. 虚拟环境 + 依赖

> `pyproject.toml` 没有 `[build-system]`，不要用 `pip install -e .`，直接列依赖安装：

```bash
cd /opt/QQbot
sudo -u qqbot python3 -m venv .venv
sudo -u qqbot .venv/bin/pip install -U pip
sudo -u qqbot .venv/bin/pip install \
  "nonebot2[fastapi,websockets]>=2.5.0" \
  nonebot-adapter-onebot httpx pillow openai \
  "sqlalchemy>=2.0" "psycopg[binary]>=3.1" "alembic>=1.13"
```

## 6. 配置 `.env`

```bash
sudo -u qqbot cp .env.example .env
sudo -u qqbot mkdir -p data
sudo chmod 600 /opt/QQbot/.env
# 用 vim 按 deploy/.env.prod.example 填真实值（数据库密码、LLM KEY、ONEBOT_WS_URLS）
```

## 7. systemd 常驻

```bash
sudo cp /opt/QQbot/deploy/qqbot.service /etc/systemd/system/
sudo cp /opt/QQbot/deploy/qqbot-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now qqbot qqbot-web
sudo systemctl status qqbot qqbot-web
```

> 说明：
> - `qqbot.service`（bot）**刻意不用 `EnvironmentFile`**，因为 systemd 会把
>   `ONEBOT_WS_URLS=["ws://..."]` 里的引号剥掉、变成非法 JSON。bot 会在启动时
>   自行读取工作目录下的 `.env`（NoneBot 默认加载），`bot.py` 也会把
>   `DATABASE_URL` 注入环境变量，所以 bot 不需要额外的环境文件。
> - `qqbot-web.service`（web）**保留 `EnvironmentFile`**，因为 FastAPI 的后端
>   直接读 `os.environ` 里的 `DATABASE_URL`，需要由环境文件提供。
>   web 进程里多余的 `ONEBOT_WS_URLS` 被剥引号也无影响，web 不读取它。

## 8. nginx 站点

```bash
sudo cp /opt/QQbot/deploy/nginx-qqbot-web.conf /etc/nginx/sites-available/qqbot-web.conf
sudo ln -sf /etc/nginx/sites-available/qqbot-web.conf /etc/nginx/sites-enabled/qqbot-web.conf
sudo nginx -t && sudo systemctl reload nginx
```

## 9. 验证

```bash
curl -s http://127.0.0.1:8600/api/stats
curl -I http://127.0.0.1/            # nginx 已转发到 Web 管理台
curl -s http://127.0.0.1:8081/api/v1/music/search?q=晴天  # go-music-api 自查
```

## 10. NapCat（单独，不在仓库）

bot 需连 NapCat 才能收发 QQ 消息。用之前学的方式在服务器装 NapCat.Linux 并登录小号，
在 WebUI `网络配置` 新建 **WebSocket 服务端** 监听 `3001`（对应 `.env` 的
`ONEBOT_WS_URLS`）。同机部署时保持 `127.0.0.1`；跨机则把 `ONEBOT_WS_URLS` 和
`QQ_MUSIC_API_BASE` 里的地址改成可达 IP，并放行相应端口（NapCat WebUI `6099` 建议只对内或加 token）。

## 11. 防火墙建议

- 对外放行：`80/443`（nginx 反代 Web）。可选 `6099`（NapCat WebUI，限源或加 token）。
- 仅对内：`5432`(PG)、`8080`(bot)、`8081`(go-music-api)、`3001`(NapCat WS)。
- 若使用 `HOST=0.0.0.0` 让 bot 被纳为反向 WS，才需放行 `8080`。
