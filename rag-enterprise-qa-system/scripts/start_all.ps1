$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) {
    Write-Host "[错误] 未找到 python，请先安装 Python 并加入 PATH" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path (Join-Path $root '.env'))) {
    Copy-Item (Join-Path $root '.env.example') (Join-Path $root '.env')
    Write-Host "已从 .env.example 生成 .env，请填写 DEEPSEEK_API_KEY 后重新启动" -ForegroundColor Yellow
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

if (Test-Port 8090) {
    Write-Host "RAG 服务已在运行，打开 http://localhost:8090/docs" -ForegroundColor Green
    try { Start-Process 'http://localhost:8090/docs' } catch {
        Write-Host "无法自动打开浏览器，请手动访问 http://localhost:8090/docs"
    }
    exit 0
}

$out = Join-Path $logs 'rag.out.log'
$err = Join-Path $logs 'rag.err.log'
$p = Start-Process -FilePath $py -ArgumentList @('-m', 'src.main') -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput $out -RedirectStandardError $err -PassThru
$p.Id | Set-Content -LiteralPath (Join-Path $logs 'rag.pid')

Write-Host "正在启动 RAG 服务（端口 8090）..." -ForegroundColor Cyan
$deadline = (Get-Date).AddSeconds(90)
$ok = $false
do {
    Start-Sleep -Seconds 2
    if (Test-Port 8090) {
        try {
            $r = Invoke-RestMethod http://localhost:8090/health -TimeoutSec 2
            $ok = ($r.status -eq 'healthy')
        } catch {
            $ok = $false
        }
    }
} until ($ok -or (Get-Date) -gt $deadline)

if ($ok) {
    Write-Host "RAG 服务启动成功" -ForegroundColor Green
    try { Start-Process 'http://localhost:8090/docs' } catch {
        Write-Host "无法自动打开浏览器，请手动访问 http://localhost:8090/docs"
    }
} else {
    Write-Host "RAG 服务启动失败，请查看 logs\rag.err.log" -ForegroundColor Red
    exit 1
}
