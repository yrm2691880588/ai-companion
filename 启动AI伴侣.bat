@echo off
setlocal
cd /d "%~dp0"

set "PS_EXE="
where pwsh >nul 2>nul
if not errorlevel 1 set "PS_EXE=pwsh"
if not defined PS_EXE (
    where powershell >nul 2>nul
    if not errorlevel 1 set "PS_EXE=powershell"
)
if not defined PS_EXE (
    echo [ERROR] PowerShell not found. Install PowerShell 7 or enable Windows PowerShell.
    pause
    exit /b 1
)

"%PS_EXE%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1" %*
if errorlevel 1 (
    echo.
    echo [ERROR] Startup failed. See the messages above.
    pause
)
