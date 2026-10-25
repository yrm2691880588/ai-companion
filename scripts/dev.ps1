# 本地开发：准备环境、起依赖、跑迁移、起服务
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

if (-not (Test-Path '.env')) {
    Copy-Item '.env.example' '.env'
    Write-Host '[1/5] 已从 .env.example 生成 .env（请填写 AI_COMPANION_MASTER_KEY 与 DeepSeek Key）' -ForegroundColor Yellow
} else {
    Write-Host '[1/5] 已存在 .env，跳过' -ForegroundColor DarkGray
}

$venv = Join-Path $root 'backend/.venv'
if (-not (Test-Path (Join-Path $venv 'Scripts/python.exe'))) {
    Write-Host '[2/5] 创建虚拟环境...' -ForegroundColor Cyan
    python -m venv $venv
} else {
    Write-Host '[2/5] 虚拟环境已存在' -ForegroundColor DarkGray
}

$py = Join-Path $venv 'Scripts/python.exe'
Write-Host '[3/5] 安装依赖（清华镜像）...' -ForegroundColor Cyan
& $py -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple --quiet -e "backend[dev]"

Write-Host '[4/5] 启动 Postgres 与 Redis...' -ForegroundColor Cyan
docker compose -f docker/docker-compose.yml up -d postgres redis

Write-Host '[5/5] 执行数据库迁移并启动 API...' -ForegroundColor Cyan
Start-Sleep -Seconds 3
Push-Location backend
try {
    & $py -m alembic upgrade head
} finally {
    Pop-Location
}
Push-Location backend
try {
    & $py -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
} finally {
    Pop-Location
}
