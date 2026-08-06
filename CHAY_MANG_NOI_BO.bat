@echo off
title J&T CARGO HCM HUB DASHBOARD - LUONG CHAY MANG NOI BO (LAN INTRANET)
color 0A
cls
echo =========================================================================
echo       J&T CARGO HCM HUB DASHBOARD - LUONG CHAY MANG NOI BO (LAN INTRANET)
echo =========================================================================
echo.
echo [1/2] Dang kiem tra dia chi IP Mang Noi Bo cua may tinh anh...
for /f "delims=" %%i in ('python -c "import socket; s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(('8.8.8.8',80)); print(s.getsockname()[0]); s.close()" 2^>nul') do set IP=%%i

if "%IP%"=="" (
    set IP=10.40.5.3
)

echo [2/2] Dia chi IP Mang Noi Bo CHINH XAC cua may anh la: %IP%
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

call npx vite --host 0.0.0.0 --port 5173
pause
