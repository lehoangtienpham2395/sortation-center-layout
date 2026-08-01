@echo off
:: Di chuyển đến thư mục làm việc
cd /d "C:\Users\lehoa\OneDrive\Desktop\testing"

:: Thiết lập encoding UTF-8
set PYTHONIOENCODING=utf-8

:: Chạy script sync và lưu log
echo ========================================== >> sync_log.txt
echo [SYNC START] %date% %time% >> sync_log.txt
py sync_to_sheets.py --sync-only >> sync_log.txt 2>&1
echo [SYNC END] %date% %time% >> sync_log.txt
echo ========================================== >> sync_log.txt
