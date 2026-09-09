@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".env" (
    echo 未找到 .env，正在从 .env.example 复制默认配置...
    copy ".env.example" ".env" >nul
)

where docker >nul 2>nul
if errorlevel 1 (
    echo [错误] 未找到 Docker，请先安装并启动 Docker Desktop。
    echo 如需本地模式，可运行：scripts\start_all.ps1
    pause
    exit /b 1
)

echo 正在构建并启动全部服务...
docker compose up -d --build
if errorlevel 1 (
    echo [错误] 服务启动失败，请检查 docker compose 输出。
    pause
    exit /b 1
)

echo 正在等待 API 服务就绪...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$deadline=(Get-Date).AddMinutes(5);" ^
  "do {" ^
  "  Start-Sleep -Seconds 3;" ^
  "  try { $api=Invoke-RestMethod http://localhost:8000/health -TimeoutSec 2; $apiOk=($api.status -eq 'healthy') } catch { $apiOk=$false };" ^
  "  try { $mem=Invoke-RestMethod http://localhost:8084/health -TimeoutSec 2; $memOk=($mem.status -eq 'healthy') } catch { $memOk=$false };" ^
  "  $ok=($apiOk -and $memOk)" ^
  "} until ($ok -or (Get-Date) -gt $deadline);" ^
  "if ($ok) { Write-Host '全部服务已就绪'; Start-Process http://localhost:8000/docs } else { Write-Host '[错误] API 或记忆服务未就绪，请运行 docker compose logs 查看日志'; exit 1 }"

pause
