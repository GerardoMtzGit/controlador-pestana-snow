@echo off
title Iniciar Chrome para Controlador de Pestanas (Puerto 9222)
echo ============================================================
echo   Iniciando Chrome con Puerto de Depuracion Remota 9222
echo ============================================================
echo.

set CHROME_PATH=""
if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" (
    set CHROME_PATH="C:\Program Files\Google\Chrome\Application\chrome.exe"
) else if exist "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" (
    set CHROME_PATH="C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
) else if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" (
    set CHROME_PATH="%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
) else if exist "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" (
    set CHROME_PATH="C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
)

if %CHROME_PATH%=="" (
    echo [ERROR] No se encontro Google Chrome ni Microsoft Edge instalado.
    pause
    exit /b 1
)

:: Usar un directorio de perfil dedicado para depuración para evitar conflicto si Chrome ya está abierto
set USER_DATA_DIR="%LOCALAPPDATA%\Google\Chrome\User Data Debug"

echo Abriendo navegador en puerto 9222...
echo Ruta: %CHROME_PATH%
echo Datos: %USER_DATA_DIR%
echo.

start "" %CHROME_PATH% --remote-debugging-port=9222 --remote-allow-origins=* --user-data-dir=%USER_DATA_DIR%

echo Listo. El navegador se ha iniciado escuchando en el puerto 9222.
timeout /t 2 >nul
exit /b 0
