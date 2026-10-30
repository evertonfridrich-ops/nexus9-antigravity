@echo off
setlocal
cd /d "%~dp0"

echo ========================================================
echo   NEXUS9 - Instalador Automatico para Windows
echo ========================================================
echo.

if "%~1"=="" (
    echo [INFO] Nenhum workspace informado na linha de comando.
    echo.
    set /p "TARGET_WORKSPACE=Digite o caminho da pasta do seu projeto (Workspace): "
) else (
    set "TARGET_WORKSPACE=%~1"
)

if "%TARGET_WORKSPACE%"=="" (
    echo [ERRO] Nenhum caminho informado. Instalacao cancelada.
    echo.
    pause
    exit /b 1
)

echo.
echo [1/2] Iniciando integracao no workspace: "%TARGET_WORKSPACE%"
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-for-your-pc.ps1" -Workspace "%TARGET_WORKSPACE%" -ReplaceExisting %2 %3 %4 %5 %6 %7 %8 %9

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================================
    echo   [SUCESSO] NEXUS9 integrado com sucesso ao Antigravity!
    echo ========================================================
    echo 1. Reinicie ou atualize os servidores MCP no Antigravity.
    echo 2. Confirme a Skill nexus9 em Customizations.
) else (
    echo.
    echo ========================================================
    echo   [ERRO] Ocorreu uma falha durante a instalacao.
    echo ========================================================
    echo Verifique se o Python 3.12 ou 3.13 (64 bits) esta instalado com PATH ativo.
)

echo.
pause
