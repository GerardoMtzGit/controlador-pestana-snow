@echo off
title Lanzador - Controlador de Pestanas ServiceNow
cd /d "%~dp0"

echo ============================================================
echo   Iniciando Controlador de Pestanas con Antigravity SDK
echo ============================================================
echo.

python -m streamlit run app_controlador.py
pause
