@echo off
REM Automated Proxy Health Check - Windows Task Scheduler Script
REM 
REM Usage:
REM   1. Open Task Scheduler (taskschd.msc)
REM   2. Create Basic Task: "Cryptobot Proxy Health Check"
REM   3. Trigger: Daily at 6:00 AM (or your preferred schedule)
REM   4. Action: Start a program
REM      - Program: C:\Users\azureuser\Repositories\cryptobot\scripts\proxy_health_check.bat
REM   5. Enable "Run whether user is logged on or not"

cd /d C:\Users\azureuser\Repositories\cryptobot

echo [%date% %time%] Starting proxy health check... >> logs\proxy_health_check.log

python scripts\proxy_health_check.py >> logs\proxy_health_check.log 2>&1

if %ERRORLEVEL% NEQ 0 (
    echo [%date% %time%] WARNING: Health check detected issues! >> logs\proxy_health_check.log
) else (
    echo [%date% %time%] Health check completed successfully >> logs\proxy_health_check.log
)

echo. >> logs\proxy_health_check.log
