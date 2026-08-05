@echo off
title HO TRO CHAY DASHBOARD KHO HCM HUB - MANG NOI BO (LAN SHARE)
color 0A
cls
echo =========================================================================
echo       J&T CARGO HCM HUB DASHBOARD - LUONG CHAY MANG NOI BO (LAN INTRANET)
echo =========================================================================
echo.
echo [1/2] Dang kiem tra dia chi IP Noi Bo cua may tinh anh...
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4 Address" /c:"IPv4"') do (
    set IP=%%a
)
set IP=%IP: =%

echo [2/2] Dia chi IP Mang Noi Bo cua may anh la: %IP%
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
