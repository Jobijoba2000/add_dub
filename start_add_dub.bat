@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
set "ROOT=%~dp0"
set "PYTHONUTF8=1"
set "ADD_DUB_OPTIONS=%~dp0options.conf"
set "PY_EXE=%ROOT%tools\python\python.exe"
set "FF_EXE=%ROOT%tools\ffmpeg\bin\ffmpeg.exe"
for %%D in (input output tmp) do if not exist "%ROOT%%%D" mkdir "%ROOT%%%D"

rem Python est prepare avec PowerShell : aucun Python systeme necessaire.
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\prepare_python.ps1"
if errorlevel 1 goto fail
"%PY_EXE%" "%ROOT%scripts\prepare_tools.py"
if errorlevel 1 goto fail

rem --- PATH local pour cette session -----------------------------------------
set "PATH=%ROOT%tools\python;%ROOT%tools\ffmpeg\bin;%ROOT%tools\MKVToolNix;%ROOT%tools\subtitle_edit;%PATH%"
set "FFMPEG_BINARY=%ROOT%tools\ffmpeg\bin\ffmpeg.exe"

rem --- Verifications minimales -----------------------------------------------
if not exist "%PY_EXE%" (
    echo [ERROR] Portable Python not found: %PY_EXE%
    pause
    exit /b 1
)
if not exist "%FF_EXE%" (
    echo [ERROR] FFmpeg not found: %FF_EXE%
    pause
    exit /b 1
)
if not exist "%ROOT%add_dub\__main__.py" (
    echo [ERROR] Module not found: add_dub\__main__.py
    pause
    exit /b 1
)

rem --- venv -------------------------------------------------------------------
if not exist "%ROOT%.venv\Scripts\python.exe" (
    echo [STEP] Creating virtual environment...
    "%PY_EXE%" -m venv "%ROOT%.venv"
    if errorlevel 1 (
        echo [ERROR] Unable to create venv with %PY_EXE%
        pause
        exit /b 1
    )
    echo [OK] venv ready.
)

call "%ROOT%.venv\Scripts\activate.bat"

rem --- Dependances ------------------------------------------------------------
if exist "%ROOT%requirements.txt" (
    set "HASH_FILE=%ROOT%.venv\.req_hash"
    set "CURR_HASH="
    for /f "tokens=*" %%H in ('python -c "import hashlib; print(hashlib.sha256(open('requirements.txt', 'rb').read()).hexdigest())"') do set "CURR_HASH=%%H"
    if not defined CURR_HASH goto fail

    set "LAST_HASH="
    if exist "!HASH_FILE!" set /p LAST_HASH=<"!HASH_FILE!"

    if "!CURR_HASH!" NEQ "!LAST_HASH!" (
        echo [STEP] Installing / updating dependencies from requirements.txt...
        python -m pip install --disable-pip-version-check --no-input --upgrade pip || goto fail
        python -m pip install --disable-pip-version-check --no-input -r "%ROOT%requirements.txt" || goto fail
        > "!HASH_FILE!" echo !CURR_HASH!
        echo [OK] Dependencies up to date.
    ) else (
        echo [INFO] Dependencies already up to date - skipping check.
    )
) else (
    echo [INFO] requirements.txt missing - step skipped.
)

rem --- Boucle d'execution -----------------------------------------------------
:loop
echo.
echo -^> Launching add_dub module

rem Si des arguments sont passes au .bat, on les relaie au module Python
if "%~1"=="" (
    python -m add_dub
) else (
    python -m add_dub %*
)

if errorlevel 1 goto fail
echo.

call "%ROOT%.venv\Scripts\deactivate.bat" 2>nul
echo Virtual environment deactivated.
pause
exit /b 0

:fail
echo [ERROR] A step failed. Check messages above.
call "%ROOT%.venv\Scripts\deactivate.bat" 2>nul
pause
exit /b 1
