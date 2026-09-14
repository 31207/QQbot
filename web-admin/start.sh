#!/usr/bin/env bash
# 启动点歌管理台（FastAPI 后端 + 静态前端）
# 用法：./web-admin/start.sh
set -e

cd "$(dirname "$0")/.."

PY=".venv/bin/python"
if [ ! -x "$PY" ]; then
    echo "未找到虚拟环境 $PY，请先创建 .venv 并安装依赖（pip install -e .）" >&2
    exit 1
fi

echo "启动管理台：http://127.0.0.1:${WEB_ADMIN_PORT:-8600}"
exec "$PY" web-admin/backend/app.py
