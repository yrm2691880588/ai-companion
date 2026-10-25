@echo off
chcp 65001 >nul
title AI 伴侣系统
cd /d "%~dp0"

where pwsh >nul 2>nul
if %errorlevel%==0 (
    pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1" %*
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1" %*
)

echo.
echo 服务已停止，按任意键关闭窗口...
pause >nul
