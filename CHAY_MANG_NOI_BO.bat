@echo off
cd /d "%~dp0"
title J&T CARGO HCM HUB DASHBOARD - LUONG CHAY MANG NOI BO (LAN INTRANET)
color 0A
cls
echo =========================================================================
echo       J&T CARGO HCM HUB DASHBOARD - LUONG CHAY MANG NOI BO (LAN INTRANET)
echo =========================================================================
echo.
echo [1/3] Dang giai phong cong 5173 de dam bao luong chay sach 100%...
powershell -Command "Get-NetTCPConnection -LocalPort 5173 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }" >nul 2>&1

echo [2/3] Dang mo tuong feu Windows (Firewall) cho Port 5173...
powershell -Command "if (-not (Get-NetFirewallRule -DisplayName 'Allow Vite Port 5173 LAN' -ErrorAction SilentlyContinue)) { New-NetFirewallRule -DisplayName 'Allow Vite Port 5173 LAN' -Direction Inbound -LocalPort 5173 -Protocol TCP -Action Allow }" >nul 2>&1

echo [3/3] Dang khoi chay Web Server Mang Noi Bo...
echo.
python server_lan.py
pause
