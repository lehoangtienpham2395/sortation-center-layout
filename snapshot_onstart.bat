@echo off
REM ============================================================
REM snapshot_onstart.bat — Fallback: chay khi bat may lai
REM Dung --force de bypass time-window guard (Write-Once guard van con)
REM Neu snapshot da ton tai (da chay 06:05 roi) -> tu dong SKIP
REM ============================================================

SET PROJECT_DIR=C:\Users\lehoa\.gemini\antigravity\scratch\sortation-center-layout
SET PYTHON=python
SET LOG_DIR=%PROJECT_DIR%\logs

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

for /f "tokens=1-3 delims=/" %%a in ("%date%") do (
    set MM=%%a
    set DD=%%b
    set YYYY=%%c
)
SET LOG_FILE=%LOG_DIR%\snapshot_onstart_%YYYY%%MM%%DD%.log

echo. >> "%LOG_FILE%"
echo [%date% %time%] === ONSTART FALLBACK TRIGGER === >> "%LOG_FILE%"

REM Cho 3 phut sau khi logon de mang kip ket noi
echo [%date% %time%] Cho 3 phut de mang khoi dong... >> "%LOG_FILE%"
timeout /t 180 /nobreak >nul
echo [%date% %time%] Het 3 phut cho, bat dau kiem tra mang... >> "%LOG_FILE%"

REM Cho mang truoc (retry moi 30s, toi da 20 lan = 10 phut)
SET /A RETRY=0
:CHECK_NET
ping -n 1 -w 2000 8.8.8.8 >nul 2>&1
IF %ERRORLEVEL% EQU 0 GOTO NET_OK
SET /A RETRY+=1
echo [%date% %time%] Cho mang... lan %RETRY%/20 >> "%LOG_FILE%"
IF %RETRY% GEQ 20 (
    echo [%date% %time%] ABORT: Khong co mang sau 20 lan. >> "%LOG_FILE%"
    exit /b 1
)
timeout /t 30 /nobreak >nul
GOTO CHECK_NET

:NET_OK
echo [%date% %time%] Mang OK >> "%LOG_FILE%"

REM Chay voi --force (bypass time guard, Write-Once guard van bao ve)
cd /d "%PROJECT_DIR%"
%PYTHON% backend_sync\sync_postgre.py >> "%LOG_FILE%" 2>&1

echo [%date% %time%] OnStart fallback ket thuc: %ERRORLEVEL% >> "%LOG_FILE%"
exit /b 0
