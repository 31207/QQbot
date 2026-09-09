param(
    [string]$Host = "127.0.0.1",
    [int]$Port = 5433,
    [string]$User = "qqbot",
    [string]$Password = "",
    [string]$Database = "qqbot"
)

# 组装 PostgreSQL 连接串并写入当前会话环境变量。
# bot(NoneBot) 与 web(FastAPI) 都读取同一环境变量 DATABASE_URL。
# 密码不硬编码：优先用参数 $Password，其次读环境变量 $env:PGPASSWORD；都不填则提示。
if (-not $Password) {
    $Password = $env:PGPASSWORD
}
if (-not $Password) {
    Write-Warning "未提供数据库密码。可用 -Password 参数，或先设置环境变量 PGPASSWORD。"
}

$env:DATABASE_URL = "postgresql+psycopg://${User}:${Password}@${Host}:${Port}/${Database}"

Write-Output "已设置 DATABASE_URL ="
Write-Output "  $env:DATABASE_URL"
Write-Output "启动 bot： .\.venv\Scripts\python.exe bot.py"
Write-Output "启动 web： .\.venv\Scripts\python.exe web-admin\backend\app.py"
Write-Output ""
Write-Output "注意：此变量只在当前 PowerShell 会话有效。"
