# add_dub — doublage TTS basé sur sous-titres (Windows)

**add_dub** prend une vidéo + des sous-titres, génère une piste voix TTS synchronisée, fait le *ducking* de l’audio d’origine, puis remuxe le tout en **MP4/MKV** avec 2 pistes audio (mix TTS par défaut + piste originale) et la piste sous-titres.

> 🎯 Plateforme : **Windows** (TTS SAPI via `pyttsx3`).
>  
> 📦 Deux modes d’usage :
> - **Recommandé** : téléchargez la **release ZIP “portable”** (tout inclus), dézippez, double-cliquez `start_add_dub.bat`.
> - **Dev (repo GitHub)** : ce dépôt contient uniquement le **code** (pas les outils). Voir “Installation développeur”.

---

## TL;DR (release portable)

1. Téléchargez la dernière release **portable** : `add_dub_portable_x.y.z.zip`.
2. Dézippez dans un dossier sans droits spéciaux (évitez `C:\Program Files`).
3. Double-cliquez `start_add_dub.bat`.
4. Mettez vos vidéos dans `input\` (SRT “sidecar” ou MKV avec ST intégrés).
5. Suivez les questions à l’écran ; la sortie est dans `output\`.

---

## Fonctionnalités

- Extraction audio d’origine, *ducking* pendant les répliques (réglable).
- Synthèse vocale **pyttsx3** (voix FR si dispo), calée à la durée des sous-titres.
- Mix **BG (audio d’origine)** + **TTS** avec niveaux réglables.
- Remux final vidéo + 2 pistes audio + sous-titres gardés (non par défaut).
- Mode **Auto** (mêmes réglages pour plusieurs fichiers) ou **Manuel** (test 5 min possible).

---

## Installation développeur (clonage du dépôt)

> ⚠️ Le repo **ne** contient **pas** les outils binaires.  
> Utilisez plutôt la **release portable** pour un usage direct.

### Prérequis (obligatoires)

- **Python 3.12** (avec `venv` et `pip`)
- **ffmpeg** + **ffprobe** (dans `PATH` ou via `tools\ffmpeg\bin\`)
- **MKVToolNix** (`mkvmerge.exe`, `mkvextract.exe`) — nécessaire pour lire/extraire les ST MKV
- **Subtitle Edit** (pour OCR si sous-titres image/PGS) + **Tesseract** avec **fr.traineddata**

### Étapes

    git clone https://github.com/<ton-user>/add_dub.git
    cd add_dub
    python -m venv .venv
    .venv\Scripts\activate
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt

- Placez les outils dans `tools\` **ou** assurez-vous qu’ils sont dans le `PATH` :
    - `tools\ffmpeg\bin\ffmpeg.exe` et `ffprobe.exe`
    - `tools\MKVToolNix\mkvmerge.exe` et `mkvextract.exe`
    - `tools\subtitle_edit\SubtitleEdit.exe`
    - `tools\subtitle_edit\Tesseract\tesseract.exe`
    - `tools\subtitle_edit\Tesseract\tessdata\fr.traineddata`

Lancez :

    start_add_dub.bat

---

## Utilisation

- Déposez vos vidéos dans `input\`.
- Le programme liste les fichiers éligibles :
  - **MKV** : s’il existe un SRT sidecar **ou** des ST intégrés.
  - **MP4** : uniquement s’il existe un SRT sidecar.
- Choisissez **Auto** (réglages communs) ou **Manuel** (réglage fin avec test court).
- Le fichier final est écrit dans `output\`.

---

## Dépannage rapide

- **“ffmpeg introuvable”** → ajoutez `ffmpeg.exe` et `ffprobe.exe` dans `tools\ffmpeg\bin\` *ou* installez ffmpeg et ajoutez-le au `PATH`.
- **“MKVToolNix absent”** → ajoutez `mkvmerge.exe` et `mkvextract.exe` dans `tools\MKVToolNix\`.
- **“Subtitle Edit/Tesseract manquant”** → ajoutez `SubtitleEdit.exe` + `Tesseract\tesseract.exe` + `Tesseract\tessdata\fr.traineddata`.
- **Voix FR introuvable** → `pyttsx3` utilisera la voix par défaut ; installez une voix française Windows si besoin.

---

## Roadmap (idées)

- Sélection de voix TTS par langue.
- Journal `.log` détaillé.
- Option “garder fichiers intermédiaires”.
- Présélections de mix (profils).

---

## Licence & tiers

- Le **code** de ce repo : voir `LICENSE`.
- Les **binaires tiers** (ffmpeg, MKVToolNix, Subtitle Edit, Tesseract) **ne sont pas** dans le repo.  
  Ils sont fournis **uniquement** dans la **release portable** avec leurs **licences** et liens sources (dossier `licenses\`).

---
