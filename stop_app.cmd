@echo off
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8501 .*LISTENING"') do taskkill /PID %%P /F >nul 2>nul
echo 问询前哨服务已停止。
pause
