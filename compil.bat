@echo off
echo =========================================
echo   Compilation de AddDub avec PyInstaller
echo =========================================
echo.
.venv\Scripts\pyinstaller.exe --noconfirm add_dub.spec
echo.
echo Copie des outils binaires vers dist\add_dub\tools...
for %%D in (ffmpeg MKVToolNix subtitle_edit) do (
    if exist "tools\%%D" (
        robocopy "tools\%%D" "dist\add_dub\tools\%%D" /E /NFL /NDL /NJH /NJS >nul
    )
)
if exist "options.example.conf" (
    copy /y "options.example.conf" "dist\add_dub\" >nul
)
echo =========================================
echo   Compilation terminee dans dist/add_dub
echo =========================================
pause
