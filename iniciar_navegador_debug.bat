@echo off
title Iniciar Chrome con Depuracion Remota (Puerto 9222)
echo ============================================================
echo   Iniciando Chrome con Puerto de Depuracion Remota 9222
echo   (Permite conectar el Asignador y Controlador de Pestanas)
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

echo Abriendo navegador con --remote-debugging-port=9222 ...
start "" %CHROME_PATH% --remote-debugging-port=9222 --remote-allow-origins=*

echo.
echo Listo. Ya puedes abrir ServiceNow o cualquier otra pestana y seleccionarla en tu programa.
timeout /t 3 >nul
exit /b 0
