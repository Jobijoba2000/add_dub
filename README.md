# add_dub : Vocalisation de Sous-titres & Doublage Automatisé pour Windows 10 / 11

📖 **[Consulter la Documentation Officielle & le Manuel d'Utilisation](https://jobijoba2000.github.io/add_dub/)**

**add_dub** transforme automatiquement les sous-titres de vos vidéos en **doublage vocal synchronisé (TTS)** avec atténuation intelligente du fond sonore (*audio ducking*).

Conçu pour l'**accessibilité** (fatigue visuelle, malvoyance, dyslexie) et le **confort d'écoute** (regarder des vidéos étrangères sans fixer l'écran), il intègre également un moteur de **traduction neuronale (IA)** pour doubler vos vidéos dans votre langue natale.

## ✨ Fonctionnalités clés

* 🪟 **Compatibilité Windows** : Conçu spécifiquement pour **Windows 10** et **Windows 11** (64 bits).
* 🎙️ **Doublage synchronisé** : Convertit les sous-titres (intégrés aux MKV ou fichiers `.srt` externes) en voix-off synchronisée avec les sous-titres.
* 🌐 **Traduction IA intégrée** : Traduit automatiquement les sous-titres vers votre langue avant vocalisation (via CTranslate2).
* 🔊 **Audio Ducking intelligent** : Baisse automatiquement le volume de la piste originale pendant les dialogues pour une clarté parfaite.
* 🗣️ **Moteurs TTS au choix** :
  * **Edge TTS** : Voix Microsoft en ligne (connexion Internet nécessaire).
  * **OneCore (Windows)** : Rapide, 100% hors-ligne avec les voix de votre système.
  * **gTTS** : Voix Google en ligne (connexion Internet nécessaire).
* 📦 **Distribution portable** : Décompressez l’archive et lancez l’application ; Python et les outils sont fournis.
* 💻 **100% CPU** : Fonctionne sans carte graphique dédiée.
* 🖥️ **Interface graphique** : Ouvrez des vidéos ou des dossiers, réglez le doublage et écoutez un extrait avant de lancer la file d’attente.
* ▶️ **Lecteur intégré** : Préparez la voix et écoutez les sous-titres sans exporter une nouvelle vidéo.
* ⚡ **Traitement par lot (Batch)** : Traitez des saisons entières ou des dossiers récursivement.

## 📥 Formats pris en charge (Entrée & Sortie)

### 🎬 Formats de sous-titres acceptés :
* **Fichiers externes (*sidecar*) :** `.srt` (placé à côté de la vidéo avec le même nom, ou dans le dossier `srt/`).
* **Pistes intégrées aux conteneurs MKV (`.mkv`) :**
  * **Formats texte** (conversion directe) : `SRT`, `ASS` / `SSA`, `WebVTT`.
  * **Formats images** (conversion automatique par **OCR**) : `PGS` (Blu-ray), `VobSub` (DVD).
* ℹ️ *Note sur les fichiers `.mp4` et `.avi`* : L'application n'extrait pas les pistes internes de ces conteneurs ; ils doivent être accompagnés d'un fichier `.srt` externe portant le même nom.

### 📦 Structure du flux :
```
[ Vidéo (MKV/MP4/AVI) + Sous-titres ]
                  ⬇️  (add_dub)
[ Nouveau fichier MKV multi-pistes ]
  ├── Piste 0 : Vidéo copiée (AVI : réencodage)
  ├── Piste 1 : Audio Mixé (Voix TTS + Fond atténué) [Par défaut]
  ├── Piste 2 : Audio Original (séparé, réencodé en stéréo)
  └── Piste 3 : Sous-titres synchronisés
```

## 🚀 Démarrage Rapide (Version Portable)

1. **[Télécharger add_dub pour Windows 10/11 (Dernière version)](https://github.com/Jobijoba2000/add_dub/releases/latest)** et dézippez l'archive où vous le souhaitez.
2. Double-cliquez sur **`add_dub.exe`** pour ouvrir l’interface graphique.
3. Cliquez sur **Ouvrir** et choisissez vos vidéos ou un dossier sur votre ordinateur.
4. Choisissez la piste audio, les sous-titres et la voix. Activez la traduction si nécessaire.
5. Vous pouvez écouter un extrait dans l’onglet **Essai** pour ajuster les réglages.
6. Cliquez sur **Ajouter à la liste d’attente**, puis sur **Démarrer**.
7. Récupérez vos vidéos doublées dans le dossier **`output/`** par défaut !

Vos vidéos restent à leur emplacement habituel : vous n’avez pas à les déplacer dans `input/`.

La distribution propose aussi **`add_dub_console.exe`** pour l’assistant console et les commandes batch, et **`add_dub_player.exe`** pour le lecteur.

## ⚡ Mode Batch & Ligne de Commande (CLI)

Pour automatiser le traitement ou intégrer `add_dub` dans des scripts, utilisez les options en ligne de commande :

* **Traiter une vidéo spécifique :**
  ```cmd
  add_dub_console.exe --batch -i "C:\Videos\film.mkv" --tts-engine edge --voice "fr-FR-DeniseNeural"
  ```

* **Traiter tout un dossier récursivement :**
  ```cmd
  add_dub_console.exe --batch -i "C:\Videos\Series" --recursive
  ```

* **Traduire et doubler (ex : Anglais vers Français) :**
  ```cmd
  add_dub_console.exe --batch -i "C:\Videos\film.mkv" --translate --translate-from en --translate-to fr --translation-engine ctranslate2 --tts-engine edge --voice "fr-FR-DeniseNeural"
  ```

* **Ajuster les volumes et l'atténuation (*ducking*) :**
  ```cmd
  add_dub_console.exe --batch -i "C:\Videos\film.mkv" --bg-mix 0.8 --tts-mix 1.2 --ducking-db -5.0
  ```

## ⚙️ Configuration (`options.conf`)

Le fichier `options.conf` permet de définir vos préférences par défaut. Vous pouvez aussi les modifier avec le bouton **Paramètres** de l’interface graphique.

> 💡 **Astuce sur le modificateur `d`** :
> Ajoutez la lettre `d` après une valeur (ex: `translate_to = fr d`) pour que l’assistant console vous pose la question au lancement. Sans la lettre `d`, la valeur est appliquée automatiquement.

**Options principales :**
* `tts_engine` : `edge`, `onecore`, ou `gtts`.
* `voice_id` : Identifiant de la voix (ex: `fr-FR-DeniseNeural`, `fr-FR-HenriNeural`).
* `translate` : `true` ou `false` (activer la traduction automatique).
* `translate_to` : Code langue cible (ex: `fr`, `en`, `es`, `de`, `ja`...).
* `db` : Niveau d'atténuation du fond sonore en dB (ex: `-5.0`).
* `bg` / `tts` : Multiplicateurs de volume pour l'audio d'origine et la voix TTS.

## 🛠️ Exécution depuis les sources (Développeurs)

Si vous souhaitez exécuter ou modifier le code source Python :

```cmd
git clone https://github.com/Jobijoba2000/add_dub.git
cd add_dub
start_add_dub.bat
```
*Le script prépare automatiquement Python, les outils et les dépendances nécessaires. Une connexion Internet est nécessaire au premier lancement. Ajoutez `--gui` pour ouvrir l’interface graphique ou `--player` pour le lecteur ; sans argument, le script ouvre l’assistant console.*

## 📄 Licence

Ce projet est sous licence **GNU General Public License v3.0 (GPLv3)**. Les outils et modèles tiers restent soumis à leurs licences respectives : voir les [notices des composants tiers](THIRD_PARTY_NOTICES.md).

## Lecteur vidéo séparé (`--player`)

Ouvrez **`add_dub_player.exe`**, puis votre vidéo avec le bouton dossier ou **Ctrl+O**. Le clic droit permet de choisir les pistes audio et sous-titres, puis de lancer **Vocaliser les sous-titres**.

Choisissez la voix, sa vitesse, les volumes et l’atténuation du fond sonore. La voix est préparée avant l’écoute ; aucune nouvelle vidéo n’est exportée. **Enregistrer les réglages** permet de les retrouver, puis **Ctrl+Maj+D** lance la préparation avec ces réglages.

La vocalisation du lecteur utilise les sous-titres intégrés à la vidéo. Pour un SRT externe ou pour traduire les sous-titres, utilisez l’interface de doublage.

## Interface de production (`--gui`)

**`add_dub.exe`** ouvre directement l’interface graphique. Le menu **Ouvrir** permet d’ajouter des vidéos ou un dossier avec ses sous-dossiers. Choisissez les pistes, la voix et les réglages communs ; vous pouvez ensuite les adapter à un dossier ou à une vidéo.

L’onglet **Essai** permet d’écouter un passage avant de lancer le doublage complet. Ajoutez les vidéos à la liste d’attente, puis cliquez sur **Démarrer**. Les fichiers traités passent dans **Terminé**. Vous pouvez choisir le dossier de sortie et ignorer les exports existants ou les remplacer.

Le bouton **Paramètres** modifie les préférences générales pour les prochains ajouts. Les réglages d’un lot et ceux du lecteur restent indépendants. L’interface est disponible en français, anglais, espagnol, allemand et italien.
