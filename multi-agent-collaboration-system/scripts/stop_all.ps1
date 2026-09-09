$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
$logs = Join-Path $root 'logs'
$pidFile = Join-Path $logs 'pids.json'

$stopped = 0

if (Test-Path $pidFile) {
    try {
        $pids = Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json
        foreach ($prop in $pids.PSObject.Properties) {
            $id = [int]$prop.Value
            if (Get-Process -Id $id -ErrorAction SilentlyContinue) {
                Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
                Write-Host ("已停止 {0}（PID {1}）" -f $prop.Name, $id)
                $stopped++
            }
        }
    } catch {}
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
}

$procs = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -match 'uvicorn' -and
    $_.CommandLine -match '(main:app|src\.main:app)' -and
    $_.CommandLine -match '--port (8000|8081|8082|8083)'
}
foreach ($proc in $procs) {
    Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
    Write-Host ("已停止残留进程（PID {0}）" -f $proc.ProcessId)
    $stopped++
}

if ($stopped -eq 0) {
    Write-Host "没有发现正在运行的服务。"
}
Write-Host "完成，可以关闭本窗口。" -ForegroundColor Green