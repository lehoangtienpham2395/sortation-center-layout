@echo off
cd /d "%~dp0"
title KHOI CHAY DASHBOARD KHO HCM HUB BANG DOCKER DESKTOP
color 0B
cls
echo =========================================================================
echo    J&T CARGO HCM HUB DASHBOARD - MO DOCKER CONTAINER CHIA SE MANG NOI BO
echo =========================================================================
echo.
echo [1/3] Dang giai phong va khoi chay Container qua Docker Desktop...
docker compose up -d --build

echo.
echo [2/3] Dang kiem tra dia chi IP Mang Noi Bo cua may tinh anh...
set IP=
for /f "delims=" %%i in ('python -c "import socket; s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(('8.8.8.8',80)); print(s.getsockname()[0]); s.close()" 2^>nul') do set IP=%%i

if "%IP%"=="" (
    set IP=10.40.5.3
)

echo.
echo =========================================================================
echo  >>> DOCKER CONTAINER DA CHAY THANH CONG TREN DOCKER DESKTOP! <<<
echo.
echo  👉 Link Localhost (Tren may anh):   http://localhost:5173/
echo  👉 Link Mang Noi Bo (Cung Wi-Fi):   http://%IP%:5173/
echo.
echo  (Anh co the dong cua so nay, Container Docker va Web Server 
echo   se tu dong chay ngam 24/7 tren Docker Desktop!)
echo =========================================================================
echo.
pause
