@echo off
chcp 65001 >nul
cd /d "%~dp0"

where docker >nul 2>nul
if errorlevel 1 (
    echo [错误] 未找到 Docker，请先启动 Docker Desktop。
    pause
    exit /b 1
)

echo 正在停止全部服务...
docker compose down
if errorlevel 1 (
    echo [错误] 停止失败，请检查 docker compose 输出。
    pause
    exit /b 1
)

echo 服务已停止，数据卷已保留。
pause
