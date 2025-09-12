@echo off
chcp 65001 >nul
setlocal

set "ROOT=%~dp0"

REM --- OUTILS PORTABLES (dans .\tools\...) ---
set "PATH=%ROOT%tools\ffmpeg\bin;%PATH%"
set "PATH=%ROOT%tools\MKVToolNix;%PATH%"
set "PATH=%ROOT%tools\subtitle_edit;%PATH%"
REM Pour pydub (évite le warning et garantit l’exécutable utilisé)
set "FFMPEG_BINARY=%ROOT%tools\ffmpeg\bin\ffmpeg.exe"

REM 1) Créer le venv si absent (avec TON python portable dans tools\python)
if not exist "%ROOT%.venv\Scripts\python.exe" (
  echo Création de l'environnement virtuel...
  "%ROOT%tools\python\python.exe" -m venv "%ROOT%.venv" || goto fail
)

REM 2) Activer le venv
call "%ROOT%.venv\Scripts\activate.bat"

REM 3) Installer les deps une seule fois
if not exist "%ROOT%.venv\.deps_ok" (
  if exist "%ROOT%requirements.txt" (
    echo Installation des dépendances...
    python -m pip install --upgrade pip || goto fail
    python -m pip install -r "%ROOT%requirements.txt" || goto fail
    echo ok > "%ROOT%.venv\.deps_ok"
  ) else (
    echo [AVERTISSEMENT] requirements.txt introuvable, je continue sans installer.
  )
)

REM 4) Boucle
:loop
echo.
echo → Lancement de add_dub.py
python "%ROOT%add_dub.py" || goto fail
echo.
set /p CHOICE=Voulez-vous traiter une autre vidéo ? (o/n) :
if /i "%CHOICE%"=="o" goto loop

REM 5) Désactiver le venv et quitter
call "%ROOT%.venv\Scripts\deactivate.bat" 2>nul
echo Environnement virtuel désactivé.
pause
exit /b 0

:fail
echo [ERREUR] Une étape a échoué. Regarde les messages ci-dessus.
call "%ROOT%.venv\Scripts\deactivate.bat" 2>nul
pause
exit /b 1
