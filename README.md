# 🎧 add_dub — Vocaliser les sous-titres de vos vidéos (Windows)

**add_dub** transforme automatiquement les sous-titres d’une vidéo en **voix parlée (TTS)** et crée une **nouvelle vidéo avec doublage audio**.  
🎯 L’objectif est simple : permettre à celles et ceux qui ont du mal à lire les sous-titres — par **fatigue visuelle** ou **malvoyance** — de **les écouter** à la place.

## 📥 En entrée
🎞️ Une vidéo avec sous-titres intégrés,  
ou une vidéo accompagnée d’un fichier `.srt`.

## 🎬 En sortie
Une vidéo au format **MKV** contenant :  
- **Piste 0** : 🎥 vidéo originale  
- **Piste 1** : 🔊 mix voix TTS + audio original  
- **Piste 2** : 🎧 audio original seul  
- **Piste 3** : 💬 sous-titres

---

## 💾 Télécharger

Version portable:  
[📥 add_dub_v0.4.1_win64.zip](https://github.com/Jobijoba2000/add_dub/releases/download/v0.4.1/add_dub_v0.4.1_win64.zip)

Ou bien :

    git clone https://github.com/Jobijoba2000/add_dub.git

---

## ⚙️ Installation & premier lancement

1️⃣ Décompressez l’archive portable **ou** clonez le dépôt.  
2️⃣ Lancez :

    start_add_dub.bat

Au **premier démarrage**, le script :
- 📦 télécharge/installe la **Toolbox** (Python portable, FFmpeg, MKVToolNix, Subtitle Edit, etc.),
- 📁 crée les dossiers : `input`, `output`, `tmp`, `srt`,
- 🧩 génère `options.conf` à partir de `options.example.conf`,
- 🚀 démarre **en mode interactif**.

---

## 🗣️ Voix TTS prises en charge

- **OneCore (Windows)** : très **rapide** et **hors ligne**, nombre de voix dépend du système.  
- **Edge TTS** : voix **naturelles**, de bonne qualité, **nécessite Internet**.  
- **gTTS** : simple et léger, voix plus **robotiques**, **nécessite Internet**.

> 💡 L’outil sait **lister les voix** disponibles et choisir automatiquement une voix de repli quand c’est possible.

---

## ⚙️ `options.conf` (mode interactif & valeurs par défaut)

Chaque ligne est de la forme :  
- `clé = valeur` → la valeur est utilisée telle quelle  
- `clé = valeur d` → **demander** la valeur au lancement (suffixe `d` pour “demander”)

> ℹ️ Tous les champs **ne tirent pas** bénéfice d’un `d`. Par exemple, `tts_engine` supporte bien le `d`.  
> `voice_id` doit généralement être renseigné directement (ou laissé vide pour laisser l’outil choisir).

Valeurs par défaut (extrait d’`options.example.conf`) :

    # dirs
    input_dir = "input"
    output_dir = "output"
    tmp_dir = "tmp"

    # tts
    tts_engine = "onecore" d
    voice_id = ""
    min_rate_tts = 1.2
    max_rate_tts = 1.8

    # output / mix / sync
    db = -5.0 d
    offset = 0 d
    offset_video = 0
    bg = 1.0 d
    tts = 1.0 d
    audio_codec = ac3
    audio_bitrate = 256
    orig_audio_lang = Original

    ask_test_before_cleanup = false

    [logging]
    console_enable = true        ; true|false
    console_level  = INFO        ; DEBUG|INFO|WARNING|ERROR

**Détails pratiques :**
- 📂 `input_dir`, `output_dir`, `tmp_dir`, `srt` : dossiers de base (créés automatiquement).
- 🧠 `tts_engine` : `onecore` | `edge` | `gtts` (peut être suffixé de `d`).
- 🎙️ `voice_id` : identifiant précis de la voix (utile surtout pour **OneCore**). Laisser vide pour laisser l’outil tenter un choix cohérent.
- ⏩ `min_rate_tts` / `max_rate_tts` : bornes de vitesse (facteur). Exemple : `1.2` à `1.8`.
- 🔉 `db` : ducking du fond (en dB, négatif → atténuation). Exemple : `-5.0`.
- ⏱️ `offset` (ms) : décalage global **sous-titres/TTS** (positif ou négatif).
- 🎞️ `offset_video` (ms) : décalage appliqué à la **vidéo**.
- 🎚️ `bg` / `tts` : gains de mix (ex. `bg=0.8`, `tts=1.1`).
- 🎧 `audio_codec` : `aac` | `ac3` | `mp3` | `flac` | `opus` | `vorbis` | `pcm_s16le` …
- 💾 `audio_bitrate` : en kb/s (appliqué aux codecs avec pertes).
- 🗂️ `orig_audio_lang` : libellé de la piste originale.
- 🎧 `ask_test_before_cleanup` : si `true` (ou avec `d`), propose **d’écouter** et remuxer **avant** de supprimer les WAV temporaires.
- 🧾 `[logging] console_enable / console_level` : affichage console et niveau.

---

## 💬 Mode interactif

Lancer simplement :

    start_add_dub.bat

Le programme :
- 🔎 **trouve** vos fichiers dans `input/` (SRT préféré : `srt/` homonyme > sidecar `.srt` > extraction auto de la 1ʳᵉ piste MKV),
- 🎛️ **propose** la piste audio source (**index FFmpeg**, base **0**),
- 🎙️ **guide** le choix du TTS/voix, des gains et décalages,
- 🎬 génère le **MKV final** dans `output/`.

> **Indexation dans l’outil :** l’interface liste les **pistes audio en commençant à 0** (index FFmpeg), et sélectionne par défaut `0`.  
> Pour les sous-titres intégrés, l’auto-sélection prend la **première piste** (équivalent **0**) si aucun `.srt` n’est trouvé.

---

## ⚡ Mode `--batch`

Traitement sans interaction (utilise `options.conf` si une option n’est pas fournie en CLI) :

    start_add_dub.bat --batch

- 📁 `--input / -i` accepte **un ou plusieurs chemins** (fichier(s) et/ou dossier(s)).  
- 🔁 `--recursive / -r` parcourt **récursivement** les sous-dossiers.  
- 🗂️ Sélection des sous-titres :
  - priorité à `srt/<nom>.srt`,
  - sinon sidecar `.srt` à côté de la vidéo,
  - sinon **extraction** de la **1ʳᵉ piste** intégrée.
- 🔊 Sélection de la piste audio source : via `--audio-index` (**index FFmpeg**, base **0**).

---

## 🧩 Toutes les options CLI (avec valeurs & exemples)

### 🧭 Sélection du mode
- `--interactive`  
  Force l’**interface interactive** (comportement par défaut si aucun mode n’est précisé).  
  Exemple :  
    start_add_dub.bat --interactive

- `--batch`  
  Lance le **traitement sans interaction**.  
  Exemple :  
    start_add_dub.bat --batch

- `--list-voices`  
  **Affiche** les voix disponibles (selon le moteur) puis quitte.  
  Exemple :  
    start_add_dub.bat --list-voices

### 📂 Entrées / parcours
- `--input PATH ...` ou `-i PATH ...`  
  Un **ou plusieurs** chemins fichier/dossier.  
  Exemples :  
    --input "D:\vid\film.mkv"  
    --input "D:\vid\serie.mkv" "D:\vid\doc.mkv"  
    -i "D:\lot"                (dossier : parcourt les vidéos détectables)

- `--recursive` ou `-r`  
  Parcourt **récursivement** les sous-dossiers (utile avec `-i dossier`).  
  Exemple :  
    -i "D:\lot" --recursive

### 🗣️ TTS & voix
- `--tts-engine {onecore,edge,gtts}`  
  Choix du **moteur TTS** (sinon `options.conf`).  
  Exemples :  
    --tts-engine onecore  
    --tts-engine edge  
    --tts-engine gtts

- `--voice VOICE_ID`  
  **Identifiant** de la voix (selon moteur). Laisser vide pour laisser l’outil choisir.  
  Exemples :  
    --voice "fr-FR-DeniseNeural"          (Edge)  
    --voice "HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech_OneCore\Voices\Tokens\MSTTS_V110_frFR_Hortense"  (OneCore)

- `--min-rate-tts FLOAT` / `--max-rate-tts FLOAT`  
  Bornes de **vitesse** (facteur).  
  Exemple :  
    --min-rate-tts 1.2 --max-rate-tts 1.8

### ⏱️ Synchronisation & mix
- `--offset-ms INT`  
  **Décalage** global des sous-titres/TTS, en **millisecondes** (positif/négatif).  
  Exemples :  
    --offset-ms 250  
    --offset-ms -120

- `--offset-video-ms INT`  
  Décalage appliqué à la **vidéo**, en **millisecondes**.  
  Exemple :  
    --offset-video-ms 80

- `--ducking-db FLOAT`  
  **Atténuation** (dB) de l’audio de fond lors des répliques TTS.  
  Exemples :  
    --ducking-db -5.0  
    --ducking-db -7.5

- `--bg-mix FLOAT` / `--tts-mix FLOAT`  
  **Gains** du fond (`bg`) et du TTS (`tts`) dans le mix.  
  Exemple :  
    --bg-mix 0.8 --tts-mix 1.0

- `--audio-index INT`  
  **Index de la piste audio source**.  
  Exemples :  
    --audio-index 1    (première piste audio FFmpeg)  
    --audio-index 2    (deuxième piste audio FFmpeg)

- `--sub SRT:INT`  
  **Sous-titres**.  
  Valeur par défaut: auto   
  `auto` Utilise le srt si présent ou prend la première piste de sous-titres (0)   
  `srt` Utilise le srt  
  `mkv` Utilise la première piste de sous-titres du mkv  
  `mkv:N` Utilise la piste N du mkv  
  Exemples :  
    --sub srt   
    --sub mkv  
	--sub mkv:0 (prend la piste 1)   
	--sub mkv:1 (prend la piste 2)

### 🎧 Codec & sortie
- `--audio-codec {aac,ac3,mp3,flac,opus,vorbis,pcm_s16le}`  
  Codec audio de la **piste finale** (mix).  
  Exemples :  
    --audio-codec ac3  
    --audio-codec aac

- `--audio-bitrate INT`  
  **Bitrate en kb/s**.  
  Exemples :  
    --audio-bitrate 256  
    --audio-bitrate 192

- `--output-dir PATH`  
  Dossier de **sortie** (sinon `output/`).  
  Exemple :  
    --output-dir "E:\exports"

- `--overwrite`  
  **Écrase** les sorties existantes.

- `--dry-run`  
  **Présente** les actions sans écrire de fichier (utile pour vérifier la config).

- `--limit-duration-sec INT`  
  Ne traite que les **N premières secondes** (tests rapides).  
  Exemple :  
    --limit-duration-sec 60

> 💡 **Sous-titres (batch)** : pas de `--sub-track` dédié. Le batch suit la priorité  
> `srt/` > sidecar `.srt` > **extraction de la 1ʳᵉ piste** intégrée (index local 0).  
> En **interactif**, vous pouvez **choisir** explicitement la source de sous-titres.

---

## 🧪 Exemples

- **Interactif (par défaut)** :
  
      start_add_dub.bat

- **Batch sur un fichier unique** :
  
      start_add_dub.bat --batch -i "C:\Videos\film.mkv" --tts-engine edge --voice "fr-FR-DeniseNeural"

- **Batch récursif sur un dossier** :
  
      start_add_dub.bat --batch -i "C:\Videos\Films" --recursive

- **Batch avec mix personnalisé & ducking** :
  
      start_add_dub.bat --batch -i "C:\Videos\film.mkv" --bg-mix 0.7 --tts-mix 1.2 --ducking-db -4.0

- **Batch avec offset & limite de durée (test)** :
  
      start_add_dub.bat --batch -i "C:\Videos\clip.mkv" --offset-ms 250 --limit-duration-sec 30

- **Forcer la piste audio source n°1 (index FFmpeg = 1)** :
  
      start_add_dub.bat --batch -i "C:\Videos\film.mkv" --audio-index 1

---

## 🖋️ OCR des sous-titres image

Si vos sous-titres sont au format **image** (PGS, VobSub, etc.), `add_dub` utilise **Subtitle Edit** et les outils de la Toolbox pour **OCRiser** automatiquement vers SRT quand c’est nécessaire.

---

## ⚙️ Commandes rapides

    start_add_dub.bat --batch      # traitement sans interaction
    start_add_dub.bat -h           # aide et options
    start_add_dub.bat --list-voices

---

## 📜 Licence

Code sous licence **MIT**. Les dépendances nécessaires sont incluses dans la Toolbox.
