@echo off
REM ============================================================
REM snapshot_daily.bat — Chay KICH HOAT NGAY KHONG CHO
REM ============================================================

SET PROJECT_DIR=C:\Users\lehoa\.gemini\antigravity\scratch\sortation-center-layout
SET PYTHON=C:\Users\lehoa\AppData\Local\Python\pythoncore-3.14-64\python.exe
SET PATH=C:\Program Files\Git\cmd;%PATH%
SET LOG_DIR=%PROJECT_DIR%\logs

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

for /f "tokens=1-3 delims=/" %%a in ("%date%") do (
    set MM=%%a
    set DD=%%b
    set YYYY=%%c
)
SET LOG_FILE=%LOG_DIR%\snapshot_%YYYY%%MM%%DD%.log

echo. >> "%LOG_FILE%"
echo [%date% %time%] =============================== >> "%LOG_FILE%"
echo [%date% %time%] SNAPSHOT DAILY START (IMMEDIATE EXECUTION) >> "%LOG_FILE%"
echo [%date% %time%] =============================== >> "%LOG_FILE%"

cd /d "%PROJECT_DIR%"
"%PYTHON%" backend_sync\sync_postgre.py >> "%LOG_FILE%" 2>&1

echo [%date% %time%] Ket thuc voi exit code: %ERRORLEVEL% >> "%LOG_FILE%"

forfiles /p "%LOG_DIR%" /m "snapshot_*.log" /d -30 /c "cmd /c del @path" 2>nul

echo [%date% %time%] SNAPSHOT DAILY END >> "%LOG_FILE%"
exit /b 0
