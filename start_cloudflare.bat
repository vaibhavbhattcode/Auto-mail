@echo off
echo ========================================
echo Bhatt Technologies Hub - Quick Deploy
echo ========================================
echo.

echo [1/2] Starting Flask App...
start cmd /k "title Flask App && python app.py"
timeout /t 3 /nobreak >nul

echo [2/2] Starting Cloudflare Tunnel...
echo.
echo Your public URL will appear below:
echo ========================================
.\cloudflared.exe tunnel --url http://localhost:5000

pause
