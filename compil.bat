@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo =========================================
echo   Compilation de AddDub avec PyInstaller
echo =========================================
if not exist ".venv\Scripts\python.exe" (
    echo [ERREUR] Environnement absent. Lancez start_add_dub.bat au prealable.
    exit /b 1
)
.venv\Scripts\python.exe -c "from PySide6 import QtWidgets; import PyInstaller, ctranslate2, sentencepiece"
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe scripts\prepare_tools.py
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm add_dub.spec
if errorlevel 1 (
    echo [ERREUR] Compilation interrompue.
    exit /b 1
)
for %%D in (ffmpeg MKVToolNix subtitle_edit mpv) do (
    if not exist "tools\%%D" (
        echo [ERREUR] Outil portable manquant : tools\%%D
        exit /b 1
    )
    robocopy "tools\%%D" "dist\add_dub\tools\%%D" /E /NFL /NDL /NJH /NJS >nul
    if errorlevel 8 exit /b 1
)
if exist "licenses" (
    robocopy "licenses" "dist\add_dub\licenses" /E /NFL /NDL /NJH /NJS >nul
    if errorlevel 8 exit /b 1
)
for %%F in (options.example.conf README.md AUDIT.md LICENSE) do (
    if exist "%%F" (
        copy /y "%%F" "dist\add_dub\" >nul
        if errorlevel 1 exit /b 1
    )
)
echo =========================================
echo   Compilation terminee dans dist\add_dub
 echo   Console : add_dub.exe
 echo   Fenetre : add_dub.exe --gui
 echo   Lecteur : add_dub.exe --player
echo =========================================
exit /b 0
