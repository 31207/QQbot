# 数据库从 SQLite 迁移到 PostgreSQL

改造后 bot 和 web 共用同一套 SQLAlchemy 数据层，通过环境变量 **`DATABASE_URL`** 切换数据库，无需改代码。

## 原理

- `db.py` 在项目根，统一提供连接工厂 + ORM 模型（`songs` / `users` / `user_requests` / `play_history`）。
- 未设置 `DATABASE_URL` 时，默认使用本地 SQLite `data/song_requests.db`，零配置、不影响本地开发。
- 设置 `DATABASE_URL` 为 PostgreSQL 连接串时，bot 与 web 都走 PG。
- 历史遗留的 `song_requests` 表（仅剩唯一索引、无代码使用）不纳入模型，不迁移。

## 本地测试用 PostgreSQL（Windows）

项目提供 `web-admin/scripts/pg_local.ps1`，配合已解压到 `D:\pg-local` 的免安装版 PostgreSQL 使用：

```powershell
# 启动已在 5433 端口监听
.\web-admin\scripts\pg_local.ps1 start

# 查看状态 / 停止
.\web-admin\scripts\pg_local.ps1 status
.\web-admin\scripts\pg_local.ps1 stop
```

首次准备（一次性）：

```powershell
D:\pg-local\pgsql\bin\initdb.exe -D D:\pg-local\data -U postgres -E UTF8 --locale=C -A trust
# 创建测试库与账号（示例）
D:\pg-local\pgsql\bin\psql.exe -h 127.0.0.1 -p 5433 -U postgres -d postgres -c "CREATE ROLE qqbot LOGIN PASSWORD 'qqbot_pw';"
D:\pg-local\pgsql\bin\psql.exe -h 127.0.0.1 -p 5433 -U postgres -d postgres -c "CREATE DATABASE qqbot_test OWNER qqbot;"
```

> 说明：`pg_ctl start` 若在某个 shell 会话里直接运行，可能随该会话结束被回收；因此本地脚本用 `Start-Process` 直接启动 `postgres.exe` 主进程，保证常驻。

## 把真实 SQLite 数据迁到 PostgreSQL

先备份真实库（建议始终备份）：把 `data/song_requests.db` 复制到 `data/_backup/`。

然后运行迁移脚本（读取 SQLite、只写 PG、可重复执行）：

```powershell
$env:DATABASE_URL = "postgresql+psycopg://qqbot:qqbot_pw@127.0.0.1:5433/qqbot_test"
python web-admin/scripts/migrate_to_pg.py
```

迁移脚本会：

1. 只读打开 SQLite（mode=ro），不修改源文件。
2. 迁移 `songs / users / user_requests / play_history` 四张在用表，并保留原 id。
3. 把 PG 的自增序列同步到 `max(id)+1`，避免继续插歌时主键冲突。

如需从其它路径读取 SQLite，可设 `SQLITE_SRC`：

```powershell
$env:SQLITE_SRC = "D:\path\song_requests.db"
```

## ECS 部署配置

### PostgreSQL（建议托管实例，如 RDS PostgreSQL / Supabase / Neon）

创建好数据库与账号后，得到一个形如的连接串：

```
postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME
```

### 设置 bot 与 web 的 `DATABASE_URL`

bot（NoneBot）与 web（FastAPI）都读取同一环境变量，在启动前导入即可。示例（PowerShell / Systemd / Docker Compose 均可）：

```powershell
$env:DATABASE_URL = "postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME"
```

启动 bot 照常 `nb run`，启动 web 照常 `python web-admin/backend/app.py`。二者现在共用同一个 PG 数据库，不再有 SQLite 单写者并发问题。

## 兼容项说明

- 旧环境变量 `WEB_ADMIN_DB` 仍兼容：在未设 `DATABASE_URL` 时，用它指定本地 SQLite 文件。
- 旧的环境变量 `WEB_ADMIN_PORT`（web 端口）仍生效。
- 模型把 `is_banned` / `selected` 映射为 `BOOLEAN`，与旧 SQLite 的 `0/1` 整型逻辑等价。
