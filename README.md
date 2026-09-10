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
* 💻 **100% CPU** : Ultra-rapide sur n'importe quel PC, sans carte graphique dédiée.
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

1. **[Télécharger add_dub (Dernière version)](https://github.com/Jobijoba2000/add_dub/releases/latest)** et dézippez l'archive où vous le souhaitez.
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

Ce projet est sous licence **GNU General Public License v3.0 (GPLv3)**. Les outils tiers inclus dans la Toolbox restent soumis à leurs licences respectives.

## Interface graphique (en cours de développement)

> **Le mode `--gui` est en chantier.** Il est disponible pour les essais, mais des bugs peuvent subsister et son interface comme ses fonctionnalités peuvent encore évoluer. Il ne constitue pas encore une version finalisée. Le mode console interactif reste le mode par défaut.

Le lancement sans argument conserve l’assistant console interactif. Pour ouvrir la fenêtre :

```cmd
add_dub.exe --gui
```

Depuis les sources :

```cmd
start_add_dub.bat --gui
```

Utilisez **Ajouter des vidéos** ou **Ajouter un dossier** pour ouvrir la fenêtre de configuration. La liste de gauche permet de sélectionner les fichiers et d’inclure les sous-dossiers. Les vidéos sans sous-titres détectés sont signalées et ne peuvent pas être sélectionnées. Choisissez parmi les pistes audio et les sous-titres détectés, puis sélectionnez le moteur vocal, la langue, la régionalisation et la voix. La traduction et les réglages audio sont également configurables.

Les réglages communs sont initialisés à partir de la première vidéo admissible du lot. Sélectionner une autre vidéo permet de personnaliser ses réglages sans modifier ceux des autres fichiers. Ajoutez ensuite le lot à la liste d’attente ; son bouton de configuration permet de le modifier avant de cliquer sur **Lancer le traitement**.

Les réglages sont initialisés depuis `options.conf` et les arguments CLI, par exemple `add_dub.exe --gui -i "C:\Videos" --tts-engine edge`. Les modifications restent propres aux lots de la session et ne réécrivent pas `options.conf`. Le journal indique les étapes et les erreurs. Le bouton d’arrêt demande l’arrêt après la vidéo en cours.

### Compilation Windows

Après préparation de l’environnement avec `start_add_dub.bat`, lancez `compil.bat`. Le script s’arrête avec un code d’erreur si la compilation ou la copie échoue. Distribuez **tout le dossier `dist\add_dub`**, qui contient l’EXE, les bibliothèques Python/Qt et les outils portables. Le même EXE propose la console par défaut et la fenêtre avec `--gui`.

Le cadre architectural et les limites repérées sont détaillés dans [AUDIT.md](AUDIT.md).

La fenêtre utilise PySide6/Qt et reste compatible avec l’agrandissement Windows et la Loupe. La dépendance est installée dans la venv du projet, créée avec le Python de `tools`.
