@echo off
chcp 65001 >nul
cd /d "%~dp0"

where docker >nul 2>nul
if errorlevel 1 (
    echo [错误] 未找到 Docker，请先启动 Docker Desktop。
    pause
    exit /b 1
)

echo 正在启动 Agent 记忆服务...
docker compose up -d --build
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep -Seconds 5; Start-Process http://localhost:8084/docs"
pause
