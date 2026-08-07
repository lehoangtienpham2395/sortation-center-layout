@echo off
REM ============================================================
REM sync_every_30min.bat — Chay KICH HOAT NGAY DONG BO 30 PHUT/LAN
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
SET LOG_FILE=%LOG_DIR%\sync_30min_%YYYY%%MM%%DD%.log

echo. >> "%LOG_FILE%"
echo [%date% %time%] === SYNC 30 MIN TRIGGER (IMMEDIATE EXECUTION) === >> "%LOG_FILE%"

cd /d "%PROJECT_DIR%"
"%PYTHON%" backend_sync\sync_postgre.py >> "%LOG_FILE%" 2>&1

echo [%date% %time%] SYNC 30 MIN END exit code: %ERRORLEVEL% >> "%LOG_FILE%"
exit /b 0
