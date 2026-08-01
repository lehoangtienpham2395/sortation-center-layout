@echo off
chcp 65001 > NUL
title VER 2 REALTIME AUTO-LIVE SERVICE
echo ============================================================
echo   HCM HUB INBOUND DASHBOARD - VER 2 REALTIME AUTO-LIVE
echo   (Daemon 30s Delta Sync + WebSocket Server Port 8088)
echo ============================================================
echo.

cd /d "%~dp0"

echo 🚀 Starting Live WebSocket Server (Port 8088)...
start "Live WebSocket Server V2" cmd /k "python live_server.py"

timeout /t 2 > NUL

echo 🚀 Starting Realtime Micro-Polling Daemon (30s)...
python daemon_sync.py

pause
