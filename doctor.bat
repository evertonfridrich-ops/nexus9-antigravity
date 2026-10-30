@echo off
setlocal
cd /d "%~dp0"

if "%~1"=="" (
    set /p "TARGET_WORKSPACE=Digite o caminho da pasta do seu projeto: "
) else (
    set "TARGET_WORKSPACE=%~1"
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0doctor.ps1" -Workspace "%TARGET_WORKSPACE%"
pause
