# 一键启动 AI 伴侣系统：检查数据库、确保前端已构建、启动后端、自动打开页面。
# 双击仓库根目录的「启动AI伴侣.bat」即可；关闭窗口即停止后端。

param(
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Url = 'http://127.0.0.1:8000/'
$Python = Join-Path $Root 'backend/.venv/Scripts/python.exe'
if (-not (Test-Path $Python)) { $Python = 'python' }

function Write-Section([string]$Text) {
    Write-Host ''
    Write-Host "== $Text ==" -ForegroundColor Magenta
}

function Ensure-Containers {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Host '未检测到 Docker，跳过数据库检查（如已本机安装 PostgreSQL 可忽略）' -ForegroundColor Yellow
        return
    }
    $running = @(docker ps --format '{{.Names}}' 2>$null)
    foreach ($name in @('companion-postgres', 'companion-redis')) {
        if ($running -notcontains $name) {
            Write-Host "启动容器 $name ..."
            docker start $name 2>$null | Out-Null
            if ($LASTEXITCODE -ne 0) {
                docker compose -f (Join-Path $Root 'docker/docker-compose.yml') up -d postgres redis | Out-Null
            }
        }
    }
    for ($i = 0; $i -lt 30; $i++) {
        docker exec companion-postgres pg_isready -U app -d companion 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { return }
        Start-Sleep -Seconds 1
    }
    Write-Host '数据库容器未在 30 秒内就绪，请检查 Docker Desktop。' -ForegroundColor Yellow
}

function Ensure-Config {
    if (-not (Test-Path (Join-Path $Root '.env'))) {
        Copy-Item (Join-Path $Root '.env.example') (Join-Path $Root '.env')
        Write-Host '已生成 .env，请填写 DeepSeek API Key 后重新启动。' -ForegroundColor Yellow
        Start-Process notepad (Join-Path $Root '.env')
    }
}

function Ensure-Frontend {
    $index = Join-Path $Root 'frontend/dist/index.html'
    if (Test-Path $index) { return }
    Write-Section '首次启动：构建前端（约 1 分钟）'
    if (-not (Get-Command pnpm -ErrorAction SilentlyContinue)) {
        Write-Host '未找到 pnpm，无法构建前端。请安装 Node.js + pnpm 后重试。' -ForegroundColor Red
        exit 1
    }
    Push-Location (Join-Path $Root 'frontend')
    try {
        pnpm install
        pnpm build
    } finally {
        Pop-Location
    }
    if (-not (Test-Path $index)) {
        Write-Host '前端构建失败，请查看上方报错。' -ForegroundColor Red
        exit 1
    }
}

Write-Host '  AI 伴侣系统 · 启动器  ' -ForegroundColor White -BackgroundColor DarkMagenta

Ensure-Config
Ensure-Containers

$listening = Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue
if ($listening) {
    Write-Host '后端已在 8000 端口运行，直接打开页面。' -ForegroundColor Green
    if (-not $NoBrowser) { Start-Process $Url }
    exit 0
}

Ensure-Frontend

if (-not $NoBrowser) {
    Start-Job -ScriptBlock {
        param($Target)
        for ($i = 0; $i -lt 60; $i++) {
            try {
                $response = Invoke-WebRequest -Uri ($Target + 'healthz') -UseBasicParsing -TimeoutSec 2
                if ($response.StatusCode -eq 200) { break }
            } catch { }
            Start-Sleep -Seconds 1
        }
        Start-Process $Target
    } -ArgumentList $Url | Out-Null
}

Write-Section '启动后端'
Write-Host "打开地址：$Url" -ForegroundColor Cyan
Write-Host '关闭本窗口即停止服务（数据库容器会保留）。' -ForegroundColor DarkGray
Write-Host ''

Push-Location (Join-Path $Root 'backend')
try {
    & $Python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
} finally {
    Pop-Location
    Get-Job | Stop-Job -ErrorAction SilentlyContinue
    Get-Job | Remove-Job -ErrorAction SilentlyContinue
}
