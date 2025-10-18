# add_dub — doublage TTS à partir de sous-titres (Windows, local, sortie MKV)

`add_dub` génère une voix TTS synchronisée à partir de sous-titres, atténue l’audio d’origine pendant les répliques (ducking), puis remuxe en **MKV** avec :

- piste audio 0 : **mix TTS + audio original** (par défaut)  
- piste audio 1 : **audio original seul**  
- sous-titres : **conservés**

Plateforme : **Windows uniquement** (TTS OneCore via `winrt`)  
Traitement : **100 % local** — aucun cloud requis.

---

## 📦 Installation

### Option 1 — Télécharger la release portable

Téléchargez l’archive ici :  
[📥 add_dub_v0.3.0_win64.zip](https://github.com/Jobijoba2000/add_dub/releases/download/v0.3.0/add_dub_v0.3.0_win64.zip)

Puis dézippez-la et lancez `start_add_dub.bat`.

Lors de la première exécution :
- téléchargement automatique de la **Toolbox** (Python portable, ffmpeg, MKVToolNix, Subtitle Edit)  
- copie de `tools\` et `licenses\` à la racine du projet  
- création des dossiers `input\`, `output\`, `tmp\`  
- création d’un venv et installation des dépendances (`requirements.txt`)  
- lancement de l’application : `python -m add_dub`

### Option 2 — Cloner le dépôt

```bat
git clone https://github.com/jobijoba2000/add_dub.git
cd add_dub
start_add_dub.bat
```

👉 En cas de blocage réseau : téléchargez manuellement la release `toolbox-vN` correspondant à `TOOLBOX_REQUIRED.txt`, dézippez-la à la racine du projet, vérifiez que `TOOLBOX_VERSION.txt` contient le même N, puis relancez.

---

## 🪟 Prérequis Windows

- Windows 10 ou 11 avec voix **OneCore** installées (Paramètres → Heure et langue → Voix)
- Espace disque suffisant pour les temporaires et les sorties
- Aucune installation manuelle de Python ou ffmpeg n’est nécessaire (tout est dans la Toolbox)

---

## 📂 Arborescence

```
input/         # vidéos sources (.mkv ou .mp4 + .srt si nécessaire)
output/        # sorties générées (toujours .mkv)
tmp/           # fichiers temporaires
srt/           # sous-titres extraits ou OCRisés
tools/         # dépendances binaires (ffmpeg, mkvmerge, Subtitle Edit…)
licenses/      # licences des outils tiers
options.example.conf  # exemple de configuration
TOOLBOX_REQUIRED.txt  # version toolbox attendue
```

---

## 📝 Formats d’entrée

- **MKV** : support complet des SRT sidecar et des pistes sous-titres intégrées (y compris PGS).
  - Les PGS sont OCR via Subtitle Edit.
  - Fallback `vobsub2srt` si Subtitle Edit échoue.
- **MP4** : supporté en entrée, **mais nécessite un fichier `.srt` sidecar**.

---

## 🧭 Modes d’utilisation

### Mode interactif

Lancé par défaut avec `start_add_dub.bat` (ou `python -m add_dub`).

1. Sélection des vidéos depuis `input\`.
2. Sélection de la voix OneCore (`voice_id` détectés automatiquement).
3. Sélection des réglages audio :
   - `ducking_db` (atténuation pendant la voix)
   - `bg_mix` / `tts_mix` (gains multiplicatifs)
   - `offset_ms` / `offset_video_ms` (décalages éventuels)
   - vitesse min/max TTS
4. Test facultatif sur un extrait court.
5. Production finale en MKV avec deux pistes audio.

Les clés marquées `d` dans `options.conf` déclenchent des questions lors de ce mode.

---

### Mode batch

Lancé en ligne de commande :

```bat
python -m add_dub --batch
```

- Traite automatiquement toutes les vidéos présentes dans `input\`.
- Peut cibler un ou plusieurs fichiers/dossiers.
- Compatible récursivité.
- Peut appliquer les réglages enregistrés dans `options.conf`.

Exemple :

```bat
python -m add_dub --batch --input "D:\films" --recursive
```

---

## ⚙️ Ligne de commande

```bat
python -m add_dub --help
```

### Modes
- `--interactive` : interface guidée
- `--batch` : traitement sans prompt
- `--list-voices` : affiche les voix OneCore disponibles

### Entrées
- `--input PATH [PATH ...]` : fichiers/dossiers
- `--recursive` : mode récursif

### Audio / TTS
- `--voice VOICE_ID`
- `--audio-index N`
- `--offset-ms N`
- `--offset-video-ms N`
- `--ducking-db X`
- `--bg-mix X`
- `--tts-mix X`
- `--min-rate-tts X`
- `--max-rate-tts X`

### Encodage / sortie
- `--audio-codec {ac3,aac,libopus,opus,flac,libvorbis,vorbis,pcm_s16le}`
- `--audio-bitrate N`
- `--output-dir PATH`
- `--overwrite`
- `--dry-run`
- `--limit-duration-sec N`

### Exemples

```bat
# Traiter tout le dossier input
python -m add_dub --batch
```

```bat
# Limiter à 5 minutes d’extrait
python -m add_dub --batch --limit-duration-sec 300
```

```bat
# Spécifier la voix et le codec
python -m add_dub --batch --voice "Microsoft Hortense - French (France)" --audio-codec aac --audio-bitrate 192
```

---

## 🧾 Configuration persistante

Le fichier `options.conf` est fusionné avec les valeurs par défaut.  
Modèle : `options.example.conf`

```ini
input_dir = "input"
output_dir = "output"
tmp_dir = "tmp"

voice_id = "" d
db = -5.0 d
offset = 0 d
offset_video = 0
bg = 1.0 d
tts = 1.0 d

audio_codec = ac3
audio_bitrate = 256
orig_audio_lang = Original

min_rate_tts = 1.2
max_rate_tts = 1.8

[logging]
console_enable = true
console_level  = INFO
```

- Les clés avec `d` sont proposées à l’utilisateur en mode interactif.
- `bg` et `tts` sont des **gains multiplicatifs**.
- `db` est une atténuation en dB appliquée pendant la voix.
- `offset` et `offset_video` permettent des ajustements fins.
- `min_rate_tts` / `max_rate_tts` bornent la vitesse TTS.

---

## 🧠 Pipeline technique (résumé)

1. Détection et extraction des sous-titres (SRT ou OCR si PGS).
2. Génération TTS OneCore synchronisée avec les timecodes.
3. Mixage audio avec ducking via FFmpeg.
4. Remux **en MKV uniquement** :
   - piste 0 : TTS + BG
   - piste 1 : BG seul
   - sous-titres alignés
   - métadonnées de titre appliquées
5. Nettoyage des fichiers temporaires.

---

## 🧰 Dépendances intégrées

- Python portable
- ffmpeg / ffprobe
- MKVToolNix
- Subtitle Edit (pour OCR PGS)
- `numpy`, `pydub`, `winrt-runtime`, `winrt-Windows.*`

---

## 🪛 Conseils pratiques

- Fournir un `.srt` sidecar si MP4.
- Ajuster `--offset-ms` pour caler voix/sous-titres.
- Ajuster `--offset-video-ms` si nécessaire au mux final.
- Jouer sur `bg_mix` et `ducking_db` pour équilibrer le mix.
- Utiliser `--limit-duration-sec` pour tester rapidement.
- Utiliser `--list-voices` pour afficher les voix disponibles.

---

## 📜 Licence

- Code : MIT (`LICENSE`)  
- Outils tiers : voir `licenses/`

---

## 🆕 Notes de version 0.3.0

- Sortie **uniquement en MKV**
- Passage complet à **TTS OneCore** (`winrt`)
- Sélection stricte des `voice_id` valides
- OCR sous-titres via Subtitle Edit, fallback vobsub2srt
- CLI batch complète et flexible
- Gestion centralisée de la configuration
- Nettoyage automatisé des temporaires
- Toolbox auto-détectée et téléchargeable
