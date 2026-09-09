@echo off
chcp 65001 >nul
cd /d "%~dp0"

where docker >nul 2>nul
if errorlevel 1 (
    echo [错误] 未找到 Docker。
    pause
    exit /b 1
)

echo 正在停止 Agent 记忆服务...
docker compose down
pause
