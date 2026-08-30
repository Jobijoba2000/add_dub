@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

echo ===================================================
echo   Lancement de l'interface graphique AddDub (GUI)
echo ===================================================

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m add_dub --gui %*
) else (
    python -m add_dub --gui %*
)
