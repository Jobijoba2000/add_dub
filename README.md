# add_dub — doublage TTS basé sur sous-titres (Windows)

**add_dub** prend une vidéo + des sous-titres, génère une piste voix TTS synchronisée, baisse l’audio d’origine pendant les répliques (*ducking*), puis remuxe le tout en **MP4/MKV** avec :
- Piste audio 1 (par défaut) : **mix TTS + audio d’origine**
- Piste audio 2 : **audio d’origine**
- Piste **sous-titres** conservée (non par défaut)

> 🎯 Plateforme : **Windows** (TTS SAPI via `pyttsx3`)  
> 📦 **Utilisateurs finaux :** téléchargez la **release ZIP “portable” (obligatoire)**  
> 🛠️ **Ce dépôt GitHub est pour les développeurs** (code uniquement, sans outils)

---

## ➤ Utilisateurs (release “portable”)

1. Téléchargez la dernière release **portable** :
   [add_dub (Windows) — releases/latest](https://github.com/jobijoba2000/add_dub/releases/latest)

2. Dézippez dans un dossier simple (évitez `C:\Program Files`)
3. Double-cliquez `start_add_dub.bat`
4. Mettez vos vidéos dans `input\` (SRT à côté **ou** MKV avec sous-titres intégrés)
5. Suivez les questions à l’écran — la sortie est dans `output\`

> La release embarque les outils nécessaires (Python portable, ffmpeg, MKVToolNix, Subtitle Edit + Tesseract FR).  
> Aucun prérequis à installer.

---

## ✨ Fonctionnalités

- *Ducking* configurable pendant les répliques (réduction en dB)
- TTS avec **pyttsx3** (détection automatique d’une voix FR si disponible)
- Mixage **BG (audio d’origine)** + **TTS** avec niveaux séparés
- Remux final vidéo + **2 pistes audio** + **sous-titres**
- Modes **Auto** (batch) ou **Manuel** (avec test 5 min possible)

---

## 🛠️ Développeurs (clonage du dépôt)

> ⚠️ Ce repo **ne contient pas** les binaires d’outils.  
> Pour **utiliser** l’outil, prenez la **release portable**.  
> Le clonage sert à **lire le code** ou **contribuer**.

### Prérequis (obligatoires côté dev)
- **Python 3.12** (avec `venv` et `pip`)
- **ffmpeg + ffprobe** (dans le `PATH` **ou** placés dans `tools\ffmpeg\bin\`)
- **MKVToolNix** (`mkvmerge.exe`, `mkvextract.exe`)
- **Subtitle Edit** (pour OCR des sous-titres image/PGS) + **Tesseract** avec **fr.traineddata**

### Installation dev (exemple)
    git clone https://github.com/jobijoba2000/add_dub.git
    cd add_dub
    python -m venv .venv
    .venv\Scripts\activate
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt

Placez les outils soit dans `tools\...`, soit dans le `PATH` :
- `tools\ffmpeg\bin\ffmpeg.exe` et `ffprobe.exe`
- `tools\MKVToolNix\mkvmerge.exe` et `mkvextract.exe`
- `tools\subtitle_edit\SubtitleEdit.exe`
- `tools\subtitle_edit\Tesseract\tesseract.exe`
- `tools\subtitle_edit\Tesseract\tessdata\fr.traineddata`

Lancez :
    start_add_dub.bat

---

## 🚀 Utilisation (rappel)

- Déposez vos vidéos dans `input\`
- **Éligibilité :**
  - **MKV** : SRT sidecar **ou** sous-titres intégrés
  - **MP4** : **SRT sidecar obligatoire**
- Choisissez **Auto** (mêmes réglages pour plusieurs fichiers) ou **Manuel**
- Le résultat est écrit dans `output\`

---

## 🧰 Dépannage rapide

- **“ffmpeg introuvable”** → ajoutez `ffmpeg.exe` + `ffprobe.exe` dans `tools\ffmpeg\bin\` ou installez ffmpeg + PATH
- **“MKVToolNix absent”** → ajoutez `mkvmerge.exe` + `mkvextract.exe` dans `tools\MKVToolNix\`
- **“Subtitle Edit/Tesseract manquant”** → `SubtitleEdit.exe` + `Tesseract\tesseract.exe` + `Tesseract\tessdata\fr.traineddata`
- **Pas de voix FR** → Windows utilisera une voix par défaut ; installez une voix FR si besoin

---

## 📌 Roadmap (idées)

- Choix de voix TTS par langue
- Journal `.log` détaillé
- Option “garder fichiers intermédiaires”
- Profils de mix prédéfinis

---

## 📄 Licence

- Code de ce dépôt : **MIT** (voir `LICENSE`)
- Les binaires tiers (ffmpeg, MKVToolNix, Subtitle Edit, Tesseract) **ne sont pas** dans ce repo ; ils sont fournis **uniquement** dans la **release portable** avec leurs licences et liens sources (dossier `licenses\` dans l’archive)
