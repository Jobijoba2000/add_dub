@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0"

rem ============================================================================
rem  start_add_dub.bat — lance add_dub et gère/installe la Toolbox en toute sécurité
rem  · Repo : contient TOOLBOX_REQUIRED.txt  (ex: 1)
rem  · Release outils : tag toolbox-vN avec add_dub_toolbox_win64.zip
rem  · Le ZIP contient : tools/, licenses/, TOOLBOX_VERSION.txt (+ éventuellement input/ output/)
rem  Sécurités :
rem    - Jamais de suppression de vos fichiers projet (input/output non touchés)
rem    - Décompression en dossier temporaire, puis copie SEULEMENT de tools/ et licenses/
rem    - Refus si paramètres de download vides, messages d’erreurs explicites
rem ============================================================================

rem --- Réglages ---------------------------------------------------------------
set "OWNER=jobijoba2000"
set "REPO=add_dub"
set "TOOLBOX_ZIP=add_dub_toolbox_win64.zip"
set "REQ_FILE=TOOLBOX_REQUIRED.txt"
set "CUR_FILE=TOOLBOX_VERSION.txt"
set "ADD_DUB_OPTIONS=%~dp0options.conf"

rem ---------------------------------------------------------------------------

set "ROOT=%~dp0"
if not exist "%ROOT%input"  mkdir "%ROOT%input"  >nul 2>&1
if not exist "%ROOT%output" mkdir "%ROOT%output" >nul 2>&1
if not exist "%ROOT%tmp"    mkdir "%ROOT%tmp"    >nul 2>&1

echo [STEP] Preparation...

rem --- Lecture version requise ------------------------------------------------
if not exist "%ROOT%%REQ_FILE%" (
    echo [ERROR] File %REQ_FILE% missing at project root.
    echo         Add a number ^(e.g. 1^) then restart.
    pause
    exit /b 1
)
set /p REQUIRED=<"%ROOT%%REQ_FILE%"
if not defined REQUIRED set "REQUIRED=0"

rem --- Lecture version locale -------------------------------------------------
set "CURRENT=0"
if exist "%ROOT%%CUR_FILE%" (
    set /p CURRENT=<"%ROOT%%CUR_FILE%"
    if not defined CURRENT set "CURRENT=0"
)

rem --- Tests de presence des outils ------------------------------------------
set "PY_EXE=%ROOT%tools\python\python.exe"
set "FF_EXE=%ROOT%tools\ffmpeg\bin\ffmpeg.exe"
set "MKV_EXE=%ROOT%tools\MKVToolNix\mkvmerge.exe"

set "NEED_TOOLS=0"
if not exist "%PY_EXE%"  set "NEED_TOOLS=1"
if not exist "%FF_EXE%"  set "NEED_TOOLS=1"
if not exist "%MKV_EXE%" set "NEED_TOOLS=1"

rem Si outils absents, force mise a jour
if "%NEED_TOOLS%"=="1" set "CURRENT=0"

rem --- Telechargement / deploiement toolbox si necessaire --------------------
if %CURRENT% LSS %REQUIRED% (
    echo [INFO] Local Toolbox=%CURRENT% / Required=%REQUIRED% -^> downloading...

    set "URL=https://github.com/%OWNER%/%REPO%/releases/download/toolbox-v%REQUIRED%/%TOOLBOX_ZIP%"
    set "TMPDL=%ROOT%tmp\toolbox_%REQUIRED%.zip"
    set "UNPACK=%ROOT%tmp\_unpack_toolbox_%REQUIRED%"

    if exist "!UNPACK!" rd /s /q "!UNPACK!" >nul 2>&1
    mkdir "!UNPACK!" >nul 2>&1

    call :download "!URL!" "!TMPDL!"
    if errorlevel 1 (
        echo [ERROR] Toolbox download failed.
        echo         URL : !URL!
        echo         Check tag toolbox-v%REQUIRED% and presence of %TOOLBOX_ZIP%.
        if exist "!UNPACK!" rd /s /q "!UNPACK!" >nul 2>&1
        if exist "!TMPDL!" del /q "!TMPDL!" >nul 2>&1
        pause
        exit /b 1
    )
    echo [OK] Archive downloaded.

    echo [STEP] Unpacking to temporary area...
    powershell -NoProfile -Command "$ProgressPreference='SilentlyContinue'; Expand-Archive -LiteralPath '!TMPDL!' -DestinationPath '!UNPACK!' -Force"
    if errorlevel 1 (
        echo [ERROR] ZIP unpacking failed.
        if exist "!UNPACK!" rd /s /q "!UNPACK!" >nul 2>&1
        if exist "!TMPDL!" del /q "!TMPDL!" >nul 2>&1
        pause
        exit /b 1
    )

    if not exist "!UNPACK!\tools\python\python.exe" (
        echo [ERROR] Invalid Toolbox: portable python not found in tools\python.
        goto :unpack_fail
    )
    if not exist "!UNPACK!\tools\ffmpeg\bin\ffmpeg.exe" (
        echo [ERROR] Invalid Toolbox: ffmpeg not found in tools\ffmpeg\bin.
        goto :unpack_fail
    )
    if not exist "!UNPACK!\tools\MKVToolNix\mkvmerge.exe" (
        echo [ERROR] Invalid Toolbox: mkvmerge not found in tools\MKVToolNix.
        goto :unpack_fail
    )

    echo [STEP] Deploying tools ^(controlled copy^)...
    robocopy "!UNPACK!\tools" "%ROOT%tools" /E /R:1 /W:1 >nul
    if errorlevel 8 (
        echo [ERROR] Failed to copy tools folder.
        goto :unpack_fail
    )
    if exist "!UNPACK!\licenses" (
        robocopy "!UNPACK!\licenses" "%ROOT%licenses" /E /R:1 /W:1 >nul
        if errorlevel 8 (
            echo [ERROR] Failed to copy licenses folder.
            goto :unpack_fail
        )
    )

    rem --- Copie NON DESTRUCTIVE de input/ et output/ si presents dans le ZIP
    rem     Objectif : fusionner sans JAMAIS ecraser un fichier deja present dans le projet
    rem     Strategie : robocopy /E + /XC /XN /XO
    rem       - /XC : ignore les fichiers "changes" (donc existants avec diff de taille/horodatage)
    rem       - /XN : ignore les fichiers plus recents cote destination
    rem       - /XO : ignore les fichiers plus anciens cote destination
    rem     → Tout fichier deja present dans %ROOT%input|output est conserve tel quel.
    if exist "!UNPACK!\input" (
        echo [INFO] Non-destructive merge of input/ from toolbox...
        robocopy "!UNPACK!\input" "%ROOT%input" /E /R:1 /W:1 /XC /XN /XO >nul
        if errorlevel 8 (
            echo [WARNING] Robocopy reported anomalies while copying input/.
        )
    )
    if exist "!UNPACK!\output" (
        echo [INFO] Non-destructive merge of output/ from toolbox...
        robocopy "!UNPACK!\output" "%ROOT%output" /E /R:1 /W:1 /XC /XN /XO >nul
        if errorlevel 8 (
            echo [WARNING] Robocopy reported anomalies while copying output/.
        )
    )

    if exist "!UNPACK!\TOOLBOX_VERSION.txt" (
        copy /y "!UNPACK!\TOOLBOX_VERSION.txt" "%ROOT%%CUR_FILE%" >nul
    ) else (
        > "%ROOT%%CUR_FILE%" echo %REQUIRED%
    )

    if exist "!UNPACK!" rd /s /q "!UNPACK!" >nul 2>&1
    if exist "!TMPDL!" del /q "!TMPDL!" >nul 2>&1

    set "CURRENT=0"
    if exist "%ROOT%%CUR_FILE%" set /p CURRENT=<"%ROOT%%CUR_FILE%"
    if "!CURRENT!" NEQ "%REQUIRED%" (
        echo [WARNING] Toolbox version mismatch: installed=!CURRENT! / required=%REQUIRED%.
        echo               Check %CUR_FILE% and ZIP content.
    ) else (
        echo [OK] Toolbox v%REQUIRED% operational.
    )
)

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
if exist "%ROOT%requirements.txt" if not exist "%ROOT%.venv\.deps_ok" (
        echo [STEP] Installing dependencies...
        python -m pip install --disable-pip-version-check --no-input --upgrade pip || goto fail
        python -m pip install --disable-pip-version-check --no-input -r "%ROOT%requirements.txt" || goto fail
        if not exist "%ROOT%.venv\.torch_cpu_fixed" (
            echo [FIX] Cleaning up potential incompatible PyTorch versions...
            python -m pip uninstall -y torch torchvision torchaudio
            echo [FIX] Installing CPU-only PyTorch...
            python -m pip install --disable-pip-version-check --no-input torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cpu || goto fail
            echo fixed> "%ROOT%.venv\.torch_cpu_fixed"
        )
        python -m pip install --disable-pip-version-check --no-input --no-deps easynmt || goto fail
        echo ok> "%ROOT%.venv\.deps_ok"
        echo [OK] Dependencies installed.
) else (
    if exist "%ROOT%.venv\.deps_ok" (
        echo [INFO] Dependencies already installed - skipping check.
    ) else (
        echo [INFO] requirements.txt missing - step skipped.
    )
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

:unpack_fail
echo [ERROR] Toolbox deployment interrupted. Nothing was overwritten in your project.
if exist "!UNPACK!" rd /s /q "!UNPACK!" >nul 2>&1
if exist "!TMPDL!" del /q "!TMPDL!" >nul 2>&1
pause
exit /b 1

rem --- Fonction download(URL, OUTFILE) ---------------------------------------
:download
    set "DL_URL=%~1"
    set "DL_OUT=%~2"
    if not defined DL_URL (
        echo [ERROR] Download URL empty. Aborting.
        exit /b 1
    )
    if not defined DL_OUT (
        echo [ERROR] Download output path empty. Aborting.
        exit /b 1
    )
    if exist "%DL_OUT%" del /q "%DL_OUT%" >nul 2>&1
    powershell -NoProfile -Command ^
        "$ProgressPreference='SilentlyContinue'; "try { Invoke-WebRequest -Uri '%DL_URL%' -OutFile '%DL_OUT%' -UseBasicParsing -Headers @{'Cache-Control'='no-cache'}; exit 0 } catch { exit 1 }"
    if exist "%DL_OUT%" ( exit /b 0 ) else ( exit /b 1 )
