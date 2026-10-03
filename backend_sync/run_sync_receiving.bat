@echo off
cd /d "C:\Users\lehoa\.gemini\antigravity\scratch\sortation-center-layout\backend_sync"
set PYTHONIOENCODING=utf-8
echo ========================================== >> sync_receiving.log
echo [SYNC RECEIVING START] %date% %time% >> sync_receiving.log
py sync_receiving_report.py --push >> sync_receiving.log 2>&1
echo [SYNC RECEIVING END] %date% %time% >> sync_receiving.log
echo ========================================== >> sync_receiving.log
