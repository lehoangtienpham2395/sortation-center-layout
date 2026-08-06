@echo off
:: Di chuyển đến thư mục làm việc chứa script Python
cd /d "C:\Users\lehoa\.gemini\antigravity\scratch\sortation-center-layout\backend_sync"

:: Thiết lập encoding UTF-8
set PYTHONIOENCODING=utf-8

:: Chạy script sync_postgre.py và lưu log
echo ========================================== >> sync_postgre.log
echo [SYNC POSTGRE START] %date% %time% >> sync_postgre.log
py -u sync_postgre.py >> sync_postgre.log 2>&1
echo [SYNC POSTGRE END] %date% %time% >> sync_postgre.log
echo ========================================== >> sync_postgre.log
