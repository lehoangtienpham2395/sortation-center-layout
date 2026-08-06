@echo off
:: Di chuyển đến thư mục làm việc chứa script Python
cd /d "C:\Users\lehoa\.gemini\antigravity\scratch\sortation-center-layout\backend_sync"

:: Thiết lập encoding UTF-8 và Unbuffered Output để log ghi ngay lập tức
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1

:: Chạy script sync_postgre.py và lưu log
echo ========================================== >> sync_postgre.log
echo [SYNC POSTGRE START] %date% %time% >> sync_postgre.log
python -u sync_postgre.py >> sync_postgre.log 2>&1
echo [SYNC POSTGRE END] %date% %time% >> sync_postgre.log
echo ========================================== >> sync_postgre.log
