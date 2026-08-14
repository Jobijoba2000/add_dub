@echo off
echo =========================================
echo   Compilation de AddDub avec PyInstaller
echo =========================================
echo.
.venv\Scripts\pyinstaller.exe --noconfirm add_dub.spec
echo.
echo =========================================
echo   Compilation terminee dans dist/add_dub
echo =========================================
pause
