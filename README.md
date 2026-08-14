# add_dub — Vocalisation de Sous-titres & Doublage Automatisé pour Windows

📖 **[Consulter la Documentation Officielle & le Manuel d'Utilisation](https://jobijoba2000.github.io/add_dub/)**

**add_dub** transforme automatiquement les sous-titres de vos vidéos en **doublage vocal synchronisé (TTS)** avec atténuation intelligente du fond sonore (*audio ducking*).

Conçu pour l'**accessibilité** (fatigue visuelle, malvoyance, dyslexie) et le **confort d'écoute** (regarder des vidéos étrangères sans fixer l'écran), il intègre également un moteur de **traduction neuronale (IA)** pour doubler vos vidéos dans votre langue natale.

---

## ✨ Fonctionnalités clés

* 🎙️ **Doublage synchronisé** : Convertit les sous-titres (intégrés ou `.srt` externes) en voix-off calée au milliseconde près.
* 🌐 **Traduction IA intégrée** : Traduit automatiquement les sous-titres vers votre langue avant vocalisation (via CTranslate2).
* 🔊 **Audio Ducking intelligent** : Baisse automatiquement le volume de la piste originale pendant les dialogues pour une clarté parfaite.
* 🗣️ **Moteurs TTS au choix** :
  * **Edge TTS** : Voix neuronales ultra-réalistes haute fidélité (connecté).
  * **OneCore (Windows)** : Rapide, 100% hors-ligne avec les voix de votre système.
  * **gTTS** : Simple et léger.
* 📦 **100% Portable** : Aucune installation complexe, fonctionne directement après extraction.
* ⚡ **Traitement par lot (Batch)** : Traitez des saisons entières ou des dossiers récursivement.

---

## 📥 En entrée & en sortie

```
[ Vidéo (MKV/MP4/AVI) + Sous-titres ] 
                  ⬇️  (add_dub)
[ Nouveau fichier MKV multi-pistes ]
  ├── Piste 0 : Vidéo originale (sans perte)
  ├── Piste 1 : Audio Mixé (Voix TTS + Fond atténué) [Par défaut]
  ├── Piste 2 : Audio Original (Isolé et préservé)
  └── Piste 3 : Sous-titres synchronisés
```

---

## 🚀 Démarrage Rapide (Version Portable)

1. **[Télécharger add_dub_win64.zip](https://github.com/Jobijoba2000/add_dub/releases)** et dézippez-le où vous le souhaitez.
2. Placez vos vidéos dans le dossier **`input/`** (avec un fichier `.srt` ou avec sous-titres intégrés).
3. Double-cliquez sur **`add_dub.exe`**.
4. Suivez l'assistant interactif (choix de la piste audio, des sous-titres, de la voix et de la langue).
5. Récupérez votre vidéo doublée dans le dossier **`output/`** !

---

## ⚡ Mode Batch & Ligne de Commande (CLI)

Pour automatiser le traitement ou intégrer `add_dub` dans des scripts, utilisez les options en ligne de commande :

* **Traiter une vidéo spécifique :**
  ```cmd
  add_dub.exe --batch -i "C:\Videos\film.mkv" --tts-engine edge --voice "fr-FR-DeniseNeural"
  ```

* **Traiter tout un dossier récursivement :**
  ```cmd
  add_dub.exe --batch -i "C:\Videos\Series" --recursive
  ```

* **Traduire et doubler (ex : Anglais vers Français) :**
  ```cmd
  add_dub.exe --batch -i "C:\Videos\film.mkv" --translate --translate-to fr --voice "fr-FR-DeniseNeural"
  ```

* **Ajuster les volumes et l'atténuation (*ducking*) :**
  ```cmd
  add_dub.exe --batch -i "C:\Videos\film.mkv" --bg-mix 0.8 --tts-mix 1.2 --ducking-db -5.0
  ```

---

## ⚙️ Configuration (`options.conf`)

Le fichier `options.conf` permet de définir vos préférences par défaut.

> 💡 **Astuce sur le modificateur `d`** : 
> Ajoutez la lettre `d` après une valeur (ex: `translate_to = fr d`) pour que `add_dub` vous demande confirmation interactivement au lancement. Sans la lettre `d`, la valeur est appliquée automatiquement.

**Options principales :**
* `tts_engine` : `edge`, `onecore`, ou `gtts`.
* `voice_id` : Identifiant de la voix (ex: `fr-FR-DeniseNeural`, `fr-FR-HenriNeural`).
* `translate` : `true` ou `false` (activer la traduction automatique).
* `translate_to` : Code langue cible (ex: `fr`, `en`, `es`, `de`, `ja`...).
* `db` : Niveau d'atténuation du fond sonore en dB (ex: `-5.0`).
* `bg` / `tts` : Multiplicateurs de volume pour l'audio d'origine et la voix TTS.

---

## 🛠️ Exécution depuis les sources (Développeurs)

Si vous souhaitez exécuter ou modifier le code source Python :

```cmd
git clone https://github.com/Jobijoba2000/add_dub.git
cd add_dub
start_add_dub.bat
```
*Le script `start_add_dub.bat` déploiera automatiquement la toolbox requise (FFmpeg, environnement virtuel et dépendances).*

---

## 📄 Licence

Ce projet est sous licence **MIT**. Les outils tiers inclus dans la Toolbox restent soumis à leurs licences respectives.
