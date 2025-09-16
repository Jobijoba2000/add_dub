# add_dub — doublage TTS basé sur sous-titres (Windows)

**add_dub** prend une vidéo + des sous-titres, génère une voix TTS synchronisée, baisse l’audio d’origine pendant les répliques (*ducking*), puis remuxe en **MP4/MKV** avec :
- Piste 1 (par défaut) : **mix TTS + audio d’origine**
- Piste 2 : **audio d’origine**
- Piste **sous-titres** conservée (non par défaut)

> 🎯 **Windows** uniquement (TTS SAPI via `pyttsx3`)  
> 🔒 100 % local (pas de cloud)

---

## 🚀 Utilisation (méthode unique)

1) **Récupérez le code**  
   - `git clone https://github.com/jobijoba2000/add_dub.git`
   - Vous pouvez directement récupérer la release de add_dub: <br>  
   [📥 Télécharger la version portable de Add Dub](https://github.com/Jobijoba2000/add_dub/releases/download/v0.2.0/add_dub_v0.2.0_win64.zip)
				
2) **Lancez** `start_add_dub.bat`  
   À la **première exécution**, le script fait tout **automatiquement** :
   - télécharge la **Toolbox** (Python portable, ffmpeg, MKVToolNix, Subtitle Edit + OCR FR) depuis les *Releases*,
   - décompresse en temporaire puis **copie uniquement** `tools\` et `licenses\` dans le projet,
   - crée `input\`, `output\`, `tmp\`,
   - crée le **venv** et installe les **dépendances Python**.

3) **Placez vos vidéos dans `input\`**
   - **MP4** : nécessite un **SRT “sidecar”** (même nom que la vidéo : `film.mp4` + `film.srt`).  
   - **MKV** : accepte **SRT sidecar** *ou* **sous-titres intégrés** (texte/PGS).

4) **Relancez** `start_add_dub.bat` (ou laissez tourner et répondez aux questions)  
   Le résultat est écrit dans **`output\`**.

---

## ❓ FAQ rapide

- **Téléchargement Toolbox bloqué (proxy/réseau)**  
  → Téléchargez manuellement la Toolbox depuis la page **Releases** (**tag `toolbox-vN`**, même **N** que dans `TOOLBOX_REQUIRED.txt`), dézippez **à la racine du projet** (vous devez obtenir `tools\` et `licenses\`), puis mettez `TOOLBOX_VERSION.txt` à `N`. Relancez le .bat.  
  Releases : <https://github.com/jobijoba2000/add_dub/releases>

- **Mise à jour**  
  - **Code** : `git pull` (ou retéléchargez le ZIP du dépôt).  

- **Voix FR absente**  
  → Windows utilisera une voix par défaut. Vous pouvez installer une voix française dans les paramètres Windows.

---

## 📂 Arborescence utile

- `input\` : vos vidéos (+ SRT éventuels, **même nom** que la vidéo)  
- `output\` : fichiers générés  
- `tmp\` : zone temporaire (download/unzip Toolbox)  
- `tools\` : binaires (installés automatiquement)  
- `licenses\` : licences des outils tiers (copiées avec la Toolbox)

---

## ✨ Fonctionnalités

- *Ducking* réglable (réduction en dB pendant les répliques)  
- TTS **pyttsx3** (détection automatique d’une voix FR si dispo)  
- Mix distinct **BG (audio d’origine)** / **TTS**  
- Remux final vidéo + **2 pistes audio** + **sous-titres**  
- Modes **Auto** (batch) et **Manuel** (test 5 min possible)

---

## 📄 Licence

- Code de ce dépôt : **MIT** (voir `LICENSE`).  
- Outils tiers (**ffmpeg**, **MKVToolNix**, **Subtitle Edit**, **Tesseract**) fournis via la **Toolbox** et accompagnés de leurs **licences** dans `licenses\`.

---

*Si quelque chose coince, ouvrez une issue en indiquant votre version de Windows, le type de vidéo et de sous-titres.*
