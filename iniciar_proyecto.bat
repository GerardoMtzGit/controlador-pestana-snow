@echo off
title Controlador de Pestanas - Inicializador y Verificador
cd /d "%~dp0"

echo ============================================================
echo   INICIANDO CONTROLADOR DE PESTANAS (SERVICENOW / WEB)
echo ============================================================
echo.
echo Ejecutando verificacion de entorno, librerias y skills...
echo.

python bootstrap.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ADVERTENCIA] El iniciador detecto un error. Presiona una tecla para cerrar...
    pause >nul
)
