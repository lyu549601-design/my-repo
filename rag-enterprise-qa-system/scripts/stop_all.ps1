$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
$logs = Join-Path $root 'logs'
$pidFile = Join-Path $logs 'rag.pid'

$stopped = 0

if (Test-Path $pidFile) {
    try {
        $id = [int](Get-Content -LiteralPath $pidFile -Raw)
        if (Get-Process -Id $id -ErrorAction SilentlyContinue) {
            Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
            taskkill /PID $id /F /T 2>$null | Out-Null
            Write-Host ("已停止 RAG 服务（PID {0}）" -f $id)
            $stopped++
        }
    } catch {}
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
}

$listeners = netstat -ano | Select-String ':8090\s+.*LISTENING'
foreach ($line in $listeners) {
    $parts = ($line.ToString() -split '\s+') | Where-Object { $_ }
    if ($parts.Count -ge 5) {
        $procId = [int]$parts[-1]
        taskkill /PID $procId /F /T 2>$null | Out-Null
        Write-Host ("已停止残留进程（PID {0}）" -f $procId)
        $stopped++
    }
}

if ($stopped -eq 0) {
    Write-Host "没有发现正在运行的 RAG 服务。"
}
Write-Host "完成，可以关闭本窗口。" -ForegroundColor Green
