@echo off
cd /d "%~dp0"
title J&T CARGO HCM HUB DASHBOARD - LUONG CHAY MANG NOI BO (LAN INTRANET)
color 0A
cls
echo =========================================================================
echo       J&T CARGO HCM HUB DASHBOARD - LUONG CHAY MANG NOI BO (LAN INTRANET)
echo =========================================================================
echo.
echo [1/4] Dang giai phong cong 5173 de dam bao luong chay sach 100%...
powershell -Command "Get-NetTCPConnection -LocalPort 5173 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }" >nul 2>&1

echo [2/4] Dang mo tuong feu Windows (Firewall) cho Port 5173...
powershell -Command "if (-not (Get-NetFirewallRule -DisplayName 'Allow Vite Port 5173 LAN' -ErrorAction SilentlyContinue)) { New-NetFirewallRule -DisplayName 'Allow Vite Port 5173 LAN' -Direction Inbound -LocalPort 5173 -Protocol TCP -Action Allow }" >nul 2>&1

echo [3/4] Dang kiem tra dia chi IP Mang Noi Bo cua may tinh anh...
set IP=
for /f "delims=" %%i in ('python -c "import socket; s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(('8.8.8.8',80)); print(s.getsockname()[0]); s.close()" 2^>nul') do set IP=%%i

if "%IP%"=="" (
    for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4 Address" /c:"IPv4"') do (
        set IP=%%a
    )
)
if "%IP%"=="" (
    set IP=10.40.5.3
)
set IP=%IP: =%

echo [4/4] Dia chi IP Mang Noi Bo CHINH XAC cua may anh la: %IP%
echo.
echo =========================================================================
echo  >>> LINK CHIA SE TRUY CAP NOI BO CHO TOAN BO CONG NHAN / BUU CUC: <<<
echo.
echo        http://%IP%:5173/
echo.
echo  (Moi may tinh, dien thoai, iPad ket noi cung Wi-Fi / LAN deu xem duoc)
echo =========================================================================
echo.
echo Dang khoi chay Web Server Mang Noi Bo... vui long KHONG tat cua so nay!
echo.

start "" "http://localhost:5173/"

if exist ".\node_modules\.bin\vite.cmd" (
    call ".\node_modules\.bin\vite.cmd" --host 0.0.0.0 --port 5173
) else (
    call npx -y vite --host 0.0.0.0 --port 5173
)
pause
