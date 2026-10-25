# 本地前端开发：安装依赖并启动 Vite（需要后端已在 8000 端口运行）
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location (Join-Path $root 'frontend')

if (-not (Test-Path 'node_modules')) {
    Write-Host '安装前端依赖（国内镜像）...' -ForegroundColor Cyan
    pnpm install --registry=https://registry.npmmirror.com
}

Write-Host '启动前端：http://127.0.0.1:5273（/v1 会代理到 127.0.0.1:8000）' -ForegroundColor Green
pnpm dev
