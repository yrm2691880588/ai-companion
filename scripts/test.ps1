# 完整验收：后端静态检查 + 单测，前端 lint + 构建 + 纯逻辑单测
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$py = Join-Path $root 'backend/.venv/Scripts/python.exe'

if (-not (Test-Path $py)) {
    Write-Host '未找到后端虚拟环境，请先创建 backend/.venv 并安装依赖' -ForegroundColor Red
    exit 1
}

$failed = @()

Push-Location (Join-Path $root 'backend')
try {
    Write-Host '== 后端代码检查 ==' -ForegroundColor Magenta
    & $py -m ruff check app tests
    if ($LASTEXITCODE -ne 0) { $failed += 'ruff check' }

    Write-Host '== 后端格式检查 ==' -ForegroundColor Magenta
    & $py -m ruff format --check app tests
    if ($LASTEXITCODE -ne 0) { $failed += 'ruff format' }

    Write-Host '== 后端单元测试 ==' -ForegroundColor Magenta
    & $py -m pytest -q @args
    if ($LASTEXITCODE -ne 0) { $failed += 'pytest' }
} finally {
    Pop-Location
}

Push-Location (Join-Path $root 'frontend')
try {
    Write-Host '== 前端代码检查 ==' -ForegroundColor Magenta
    & pnpm lint
    if ($LASTEXITCODE -ne 0) { $failed += 'eslint' }

    Write-Host '== 前端类型与构建 ==' -ForegroundColor Magenta
    & pnpm build
    if ($LASTEXITCODE -ne 0) { $failed += 'build' }

    Write-Host '== 前端纯逻辑单测 ==' -ForegroundColor Magenta
    & pnpm test
    if ($LASTEXITCODE -ne 0) { $failed += 'frontend test' }
} finally {
    Pop-Location
}

if ($failed.Count -gt 0) {
    Write-Host ''
    Write-Host ('失败项：' + ($failed -join '、')) -ForegroundColor Red
    exit 1
}

Write-Host ''
Write-Host '全部通过' -ForegroundColor Green
exit 0
