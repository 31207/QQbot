param(
    [ValidateSet("start", "stop", "status")]
    [string]$Action = "status"
)

$pgHome = "D:\pg-local\pgsql\bin"
$pgData = "D:\pg-local\data"
$pgPort = 5433
$pgLog = "D:\pg-local\pg.log"

if (-not (Test-Path "$pgHome\pg_ctl.exe")) {
    Write-Error "未找到 PostgreSQL：$pgHome\pg_ctl.exe。请先解压免安装版到 D:\pg-local。"
    exit 1
}

switch ($Action) {
    "start" {
        Write-Output "启动 PostgreSQL（端口 $pgPort，数据目录 $pgData）..."
        # 直接启动 postgres.exe 主进程（与 web 服务同款 Start-Process，可跨会话常驻）
        Start-Process -FilePath "$pgHome\postgres.exe" -ArgumentList @("-D", $pgData, "-p", "$pgPort") -WindowStyle Hidden
        Start-Sleep -Seconds 3
        if (Get-NetTCPConnection -LocalPort $pgPort -State Listen -ErrorAction SilentlyContinue) {
            Write-Output "OK：PostgreSQL 已在端口 $pgPort 监听。"
        } else {
            Write-Output "警告：未检测到 $pgPort 监听，请检查 $pgLog。"
        }
    }
    "stop" {
        Write-Output "停止 PostgreSQL ..."
        & "$pgHome\pg_ctl.exe" -D $pgData stop
    }
    "status" {
        & "$pgHome\pg_ctl.exe" -D $pgData status
    }
}
