@echo off
chcp 65001 >nul
title QQ Bot - One Click Start
cd /d "%~dp0"

rem ================================================================
rem  Step 1: Start NapCat (opens a new window, may ask UAC/admin,
rem          then scan QR with the QQ mini account).
rem  Path: D:\qq-bot\napcat\napcat\launcher-win10.bat
rem ================================================================
echo [1/2] Starting NapCat (quick login QQ 1951701741) ...
start "NapCat" cmd /c "cd /d D:\qq-bot\napcat\napcat && launcher-win10.bat -q 1951701741"

rem ================================================================
rem  Step 2: Start the QQ Bot (NoneBot2) in this window.
rem  Wait for: "Uvicorn running on http://127.0.0.1:8080"
rem ================================================================
echo.
echo [2/2] Starting QQ Bot (NoneBot2) ...
if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] .venv not found. Run:
    echo   python -m venv .venv
    echo   .venv\Scripts\python.exe -m pip install -U "nonebot2[fastapi]" nonebot-adapter-onebot
    pause
    exit /b 1
)
".venv\Scripts\python.exe" bot.py

echo.
echo ============================================
echo   Bot stopped.
echo ============================================
pause
