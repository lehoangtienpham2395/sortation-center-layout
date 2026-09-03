@echo off
REM ==========================================================================
REM sync_jfs_2hours.bat -- Tu dong dong bo JFS ETLen 2 tieng/lan (11:00 - 22:00)
REM ==========================================================================

SET PROJECT_DIR=C:\Users\lehoa\.gemini\antigravity\scratch\sortation-center-layout
SET PYTHON=C:\Users\lehoa\AppData\Local\Python\pythoncore-3.14-64\python.exe
SET PATH=C:\Program Files\Git\cmd;%PATH%
SET LOG_DIR=%PROJECT_DIR%\logs

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
SET LOG_FILE=%LOG_DIR%\sync_2hours.log

echo. >> "%LOG_FILE%"
echo ========================================================================= >> "%LOG_FILE%"
echo [%date% %time%] === BAT DAU DONG BO JFS ETL (11:00 - 22:00) === >> "%LOG_FILE%"
echo ========================================================================== >> "%LOG_FILE%"

cd /d "%PROJECT_DIR%"
"%PYTHON%" backend_sync\sync_postgre.py >> "%LOG_FILE%" 2>&1

echo [%date% %time%] === KET THUC DONG BO (Exit Code: %ERRORLEVEL%) === >> "%LOG_FILE%"
exit /b %ERRORLEVEL%
