$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) {
    Write-Host "[错误] 未找到 python，请先安装 Python 并勾选 Add to PATH" -ForegroundColor Red
    exit 1
}

$logs = Join-Path $root 'logs'
New-Item -ItemType Directory -Force -Path $logs | Out-Null

function Test-Port([int]$port) {
    try {
        $c = New-Object System.Net.Sockets.TcpClient
        $iar = $c.BeginConnect('127.0.0.1', $port, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne(400)
        $c.Close()
        return $ok
    } catch {
        return $false
    }
}

if (Test-Port 8000) {
    Write-Host "系统已在运行，直接打开验收页面 http://localhost:8000/docs" -ForegroundColor Green
    Start-Process 'http://localhost:8000/docs'
    exit 0
}

$services = @(
    @{ Name = 'search';    Dir = (Join-Path $root 'mcp-servers\search-server');    Port = 8081; Module = 'main:app' },
    @{ Name = 'financial'; Dir = (Join-Path $root 'mcp-servers\financial-server'); Port = 8082; Module = 'main:app' },
    @{ Name = 'cleaner';   Dir = (Join-Path $root 'mcp-servers\cleaner-server');   Port = 8083; Module = 'main:app' },
    @{ Name = 'api';       Dir = $root;                                            Port = 8000; Module = 'src.main:app' }
)

$pids = @{}
foreach ($s in $services) {
    if (Test-Port $s.Port) {
        Write-Host ("[{0}] 端口 {1} 已被占用，跳过启动" -f $s.Name, $s.Port) -ForegroundColor Yellow
        continue
    }
    $out = Join-Path $logs ($s.Name + '.out.log')
    $err = Join-Path $logs ($s.Name + '.err.log')
    $p = Start-Process -FilePath $py -ArgumentList @('-m', 'uvicorn', $s.Module, '--host', '0.0.0.0', '--port', "$($s.Port)") -WorkingDirectory $s.Dir -WindowStyle Hidden -RedirectStandardOutput $out -RedirectStandardError $err -PassThru
    $pids[$s.Name] = $p.Id
    Write-Host ("[启动] {0}（端口 {1}）" -f $s.Name, $s.Port) -ForegroundColor Cyan
}

if ($pids.Count -gt 0) {
    $pids | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $logs 'pids.json') -Encoding UTF8
}

Write-Host ""
Write-Host "正在等待服务启动（约 12 秒）..." -ForegroundColor Cyan
Start-Sleep -Seconds 12

$allOk = $true
foreach ($s in $services) {
    $ok = Test-Port $s.Port
    $state = if ($ok) { "OK" } else { "FAIL" }
    if (-not $ok) { $allOk = $false }
    Write-Host ("  {0,-10} 端口 {1,-5} {2}" -f $s.Name, $s.Port, $state)
}

if ($allOk) {
    Write-Host ""
    Write-Host "全部服务启动成功！正在打开验收页面 http://localhost:8000/docs" -ForegroundColor Green
    Start-Process 'http://localhost:8000/docs'
} else {
    Write-Host ""
    Write-Host "部分服务未启动成功，请查看 logs 目录下的日志文件，或关闭占用端口的程序后重新双击启动。" -ForegroundColor Red
}