@echo off
cd /d "%~dp0"
title DUNG DASHBOARD DOCKER CONTAINER
color 0C
cls
echo =========================================================================
echo           J&T CARGO HCM HUB DASHBOARD - TAT DOCKER CONTAINER
echo =========================================================================
echo.
echo Dang tat luong chia se va dung Docker Container...
docker compose down

echo.
echo ✅ Da dung va ngat luong chia se Dashboard qua Docker thanh cong!
echo =========================================================================
echo.
pause
