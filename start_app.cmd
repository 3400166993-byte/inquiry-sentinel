@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_server.ps1"
start "" "http://localhost:8501/"
exit /b 0
