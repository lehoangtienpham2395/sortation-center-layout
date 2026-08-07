@echo off
REM ============================================================
REM snapshot_daily.bat — Chay luc 06:05 AM moi ngay
REM  - Cho mang truoc khi chay (retry moi 30 giay, toi da 30 lan)
REM  - Log vao logs\snapshot_YYYYMMDD.log
REM ============================================================

SET PROJECT_DIR=C:\Users\lehoa\.gemini\antigravity\scratch\sortation-center-layout
SET PYTHON=python
SET LOG_DIR=%PROJECT_DIR%\logs

REM Tao thu muc logs neu chua ton tai
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

REM Log file theo ngay (dinh dang YYYYMMDD)
for /f "tokens=1-3 delims=/" %%a in ("%date%") do (
    set MM=%%a
    set DD=%%b
    set YYYY=%%c
)
SET LOG_FILE=%LOG_DIR%\snapshot_%YYYY%%MM%%DD%.log

echo. >> "%LOG_FILE%"
echo [%date% %time%] =============================== >> "%LOG_FILE%"
echo [%date% %time%] SNAPSHOT DAILY START >> "%LOG_FILE%"
echo [%date% %time%] =============================== >> "%LOG_FILE%"

REM ── BUOC 1: CHO MANG (retry moi 30 giay, toi da 30 lan = 15 phut) ──────
SET /A RETRY=0
SET /A MAX_RETRY=30

:CHECK_NETWORK
ping -n 1 -w 2000 8.8.8.8 >nul 2>&1
IF %ERRORLEVEL% EQU 0 GOTO NETWORK_OK

SET /A RETRY+=1
echo [%date% %time%] Mang chua san sang (lan %RETRY%/%MAX_RETRY%) — cho 30 giay... >> "%LOG_FILE%"

IF %RETRY% GEQ %MAX_RETRY% (
    echo [%date% %time%] ABORT — Khong co mang sau %MAX_RETRY% lan thu. Bao cao anh check lai. >> "%LOG_FILE%"
    exit /b 1
)

timeout /t 30 /nobreak >nul
GOTO CHECK_NETWORK

:NETWORK_OK
echo [%date% %time%] Mang OK sau %RETRY% lan thu >> "%LOG_FILE%"

REM ── BUOC 2: CHAY SNAPSHOT ────────────────────────────────────────────────
cd /d "%PROJECT_DIR%"
echo [%date% %time%] Dang chay: python backend_sync\sync_postgre.py >> "%LOG_FILE%"

%PYTHON% backend_sync\sync_postgre.py >> "%LOG_FILE%" 2>&1

echo [%date% %time%] Ket thuc voi exit code: %ERRORLEVEL% >> "%LOG_FILE%"

REM ── BUOC 3: Giu lai 30 ngay log, xoa log cu hon ──────────────────────────
forfiles /p "%LOG_DIR%" /m "snapshot_*.log" /d -30 /c "cmd /c del @path" 2>nul

echo [%date% %time%] SNAPSHOT DAILY END >> "%LOG_FILE%"
exit /b 0
