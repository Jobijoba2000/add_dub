@echo off
setlocal EnableExtensions
set "PYTHONUTF8=1"
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo [ERREUR] Environnement absent. Lancez start_add_dub.bat au prealable.
    exit /b 1
)
.venv\Scripts\python.exe scripts\compile_release.py %*
exit /b %errorlevel%
