# 跑后端测试
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$py = Join-Path $root 'backend/.venv/Scripts/python.exe'

if (-not (Test-Path $py)) {
    Write-Host '未找到虚拟环境，请先运行 scripts/dev.ps1' -ForegroundColor Red
    exit 1
}

Push-Location (Join-Path $root 'backend')
try {
    & $py -m pytest -q @args
    $code = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $code
