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

echo [ETAPE] Preparation...

rem --- Lecture version requise ------------------------------------------------
if not exist "%ROOT%%REQ_FILE%" (
    echo [ERREUR] Fichier %REQ_FILE% manquant a la racine du projet.
    echo         Ajoutez un numero ^(ex. 1^) puis relancez.
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
    echo [INFO] Toolbox locale=%CURRENT% / requise=%REQUIRED% → telechargement...

    set "URL=https://github.com/%OWNER%/%REPO%/releases/download/toolbox-v%REQUIRED%/%TOOLBOX_ZIP%"
    set "TMPDL=%ROOT%tmp\toolbox_%REQUIRED%.zip"
    set "UNPACK=%ROOT%tmp\_unpack_toolbox_%REQUIRED%"

    if exist "!UNPACK!" rd /s /q "!UNPACK!" >nul 2>&1
    mkdir "!UNPACK!" >nul 2>&1

    call :download "!URL!" "!TMPDL!"
    if errorlevel 1 (
        echo [ERREUR] Echec du telechargement de la toolbox.
        echo         URL : !URL!
        echo         Verifiez le tag toolbox-v%REQUIRED% et la presence de %TOOLBOX_ZIP%.
        if exist "!UNPACK!" rd /s /q "!UNPACK!" >nul 2>&1
        if exist "!TMPDL!" del /q "!TMPDL!" >nul 2>&1
        pause
        exit /b 1
    )
    echo [OK] Archive telechargee.

    echo [ETAPE] Decompression en zone temporaire...
    powershell -NoProfile -Command "$ProgressPreference='SilentlyContinue'; Expand-Archive -LiteralPath '!TMPDL!' -DestinationPath '!UNPACK!' -Force"
    if errorlevel 1 (
        echo [ERREUR] Echec de la decompression du ZIP.
        if exist "!UNPACK!" rd /s /q "!UNPACK!" >nul 2>&1
        if exist "!TMPDL!" del /q "!TMPDL!" >nul 2>&1
        pause
        exit /b 1
    )

    if not exist "!UNPACK!\tools\python\python.exe" (
        echo [ERREUR] Toolbox invalide : python portable introuvable dans tools\python.
        goto :unpack_fail
    )
    if not exist "!UNPACK!\tools\ffmpeg\bin\ffmpeg.exe" (
        echo [ERREUR] Toolbox invalide : ffmpeg introuvable dans tools\ffmpeg\bin.
        goto :unpack_fail
    )
    if not exist "!UNPACK!\tools\MKVToolNix\mkvmerge.exe" (
        echo [ERREUR] Toolbox invalide : mkvmerge introuvable dans tools\MKVToolNix.
        goto :unpack_fail
    )

    echo [ETAPE] Deploiement des outils ^(copie controlee^)...
    robocopy "!UNPACK!\tools" "%ROOT%tools" /E /R:1 /W:1 >nul
    if errorlevel 8 (
        echo [ERREUR] Echec de copie du dossier tools.
        goto :unpack_fail
    )
    if exist "!UNPACK!\licenses" (
        robocopy "!UNPACK!\licenses" "%ROOT%licenses" /E /R:1 /W:1 >nul
        if errorlevel 8 (
            echo [ERREUR] Echec de copie du dossier licenses.
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
        echo [INFO] Fusion non destructive de input/ depuis la toolbox...
        robocopy "!UNPACK!\input" "%ROOT%input" /E /R:1 /W:1 /XC /XN /XO >nul
        if errorlevel 8 (
            echo [AVERTISSEMENT] Robocopy a signale des anomalies lors de la copie de input/.
        )
    )
    if exist "!UNPACK!\output" (
        echo [INFO] Fusion non destructive de output/ depuis la toolbox...
        robocopy "!UNPACK!\output" "%ROOT%output" /E /R:1 /W:1 /XC /XN /XO >nul
        if errorlevel 8 (
            echo [AVERTISSEMENT] Robocopy a signale des anomalies lors de la copie de output/.
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
        echo [AVERTISSEMENT] Mismatch version toolbox : installee=!CURRENT! / requise=%REQUIRED%.
        echo               Controlez %CUR_FILE% et le contenu du ZIP.
    ) else (
        echo [OK] Toolbox v%REQUIRED% operationnelle.
    )
)

rem --- PATH local pour cette session -----------------------------------------
set "PATH=%ROOT%tools\python;%ROOT%tools\ffmpeg\bin;%ROOT%tools\MKVToolNix;%ROOT%tools\subtitle_edit;%PATH%"
set "FFMPEG_BINARY=%ROOT%tools\ffmpeg\bin\ffmpeg.exe"

rem --- Verifications minimales -----------------------------------------------
if not exist "%PY_EXE%" (
    echo [ERREUR] Python portable introuvable : %PY_EXE%
    pause
    exit /b 1
)
if not exist "%FF_EXE%" (
    echo [ERREUR] FFmpeg introuvable : %FF_EXE%
    pause
    exit /b 1
)
if not exist "%ROOT%add_dub\__main__.py" (
    echo [ERREUR] Module introuvable : add_dub\__main__.py
    pause
    exit /b 1
)

rem --- venv -------------------------------------------------------------------
if not exist "%ROOT%.venv\Scripts\python.exe" (
    echo [ETAPE] Creation de l'environnement virtuel...
    "%PY_EXE%" -m venv "%ROOT%.venv"
    if errorlevel 1 (
        echo [ERREUR] Impossible de creer le venv avec %PY_EXE%
        pause
        exit /b 1
    )
    echo [OK] venv pret.
)

call "%ROOT%.venv\Scripts\activate.bat"

rem --- Dependances ------------------------------------------------------------
if exist "%ROOT%requirements.txt" (
    if not exist "%ROOT%.venv\.deps_ok" (
        echo [ETAPE] Installation des dependances...
        python -m pip install --disable-pip-version-check --no-input --upgrade pip || goto fail
        python -m pip install --disable-pip-version-check --no-input -r "%ROOT%requirements.txt" || goto fail
        echo ok> "%ROOT%.venv\.deps_ok"
        echo [OK] Dependances installees.
    )
) else (
    echo [INFO] requirements.txt absent — etape ignoree.
)

rem --- Boucle d'execution -----------------------------------------------------
:loop
echo.
echo → Lancement du module add_dub

rem Si des arguments sont passes au .bat, on les relaie au module Python
if "%~1"=="" (
    python -m add_dub
) else (
    python -m add_dub %*
)

if errorlevel 1 goto fail
echo.

call "%ROOT%.venv\Scripts\deactivate.bat" 2>nul
echo Environnement virtuel desactive.
pause
exit /b 0

:fail
echo [ERREUR] Une etape a echoue. Consultez les messages ci-dessus.
call "%ROOT%.venv\Scripts\deactivate.bat" 2>nul
pause
exit /b 1

:unpack_fail
echo [ERREUR] Deploiement de la toolbox interrompu. Rien n'a ete ecrase dans votre projet.
if exist "!UNPACK!" rd /s /q "!UNPACK!" >nul 2>&1
if exist "!TMPDL!" del /q "!TMPDL!" >nul 2>&1
pause
exit /b 1

rem --- Fonction download(URL, OUTFILE) ---------------------------------------
:download
    set "DL_URL=%~1"
    set "DL_OUT=%~2"
    if not defined DL_URL (
        echo [ERREUR] URL de telechargement vide. Abandon.
        exit /b 1
    )
    if not defined DL_OUT (
        echo [ERREUR] Chemin de sortie vide pour le telechargement. Abandon.
        exit /b 1
    )
    if exist "%DL_OUT%" del /q "%DL_OUT%" >nul 2>&1
    powershell -NoProfile -Command ^
        "$ProgressPreference='SilentlyContinue'; "try { Invoke-WebRequest -Uri '%DL_URL%' -OutFile '%DL_OUT%' -UseBasicParsing -Headers @{'Cache-Control'='no-cache'}; exit 0 } catch { exit 1 }"
    if exist "%DL_OUT%" ( exit /b 0 ) else ( exit /b 1 )
