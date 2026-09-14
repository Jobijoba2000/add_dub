# add_dub — Vocalisation de Sous-titres & Doublage Automatisé pour Windows 10 / 11

📖 **[Consulter la Documentation Officielle & le Manuel d'Utilisation](https://jobijoba2000.github.io/add_dub/)**

**add_dub** transforme automatiquement les sous-titres de vos vidéos en **doublage vocal synchronisé (TTS)** avec atténuation intelligente du fond sonore (*audio ducking*).

Conçu pour l'**accessibilité** (fatigue visuelle, malvoyance, dyslexie) et le **confort d'écoute** (regarder des vidéos étrangères sans fixer l'écran), il intègre également un moteur de **traduction neuronale (IA)** pour doubler vos vidéos dans votre langue natale.

---

## ✨ Fonctionnalités clés

* 🪟 **Compatibilité Windows** : Conçu spécifiquement pour **Windows 10** et **Windows 11** (64 bits).
* 🎙️ **Doublage synchronisé** : Convertit les sous-titres (intégrés aux MKV ou fichiers `.srt` externes) en voix-off calée à la milliseconde près.
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
  ├── Piste 0 : Vidéo originale (sans perte)
  ├── Piste 1 : Audio Mixé (Voix TTS + Fond atténué) [Par défaut]
  ├── Piste 2 : Audio Original (Isolé et préservé)
  └── Piste 3 : Sous-titres synchronisés
```

---

## 🚀 Démarrage Rapide (Version Portable)

1. **[Télécharger add_dub pour Windows 10/11 (Dernière version)](https://github.com/Jobijoba2000/add_dub/releases/latest)** et dézippez l'archive où vous le souhaitez.
2. Placez vos vidéos dans le dossier **`input/`** (avec un fichier `.srt` ou un fichier `.mkv` avec sous-titres intégrés).
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
*Le script `start_add_dub.bat` prépare Python avec `scripts/prepare_python.ps1`, puis lance `scripts/prepare_tools.py` pour télécharger séparément FFmpeg, MKVToolNix, Subtitle Edit, Tesseract et mpv dans `tools/`. Les archives sont vérifiées par SHA-256 et conservées dans `.cache/`. Il crée ensuite l'environnement virtuel et installe les dépendances. Les modèles OCR restent téléchargés à la demande par add_dub. Subtitle Edit nécessite .NET Framework 4.8 sur Windows.*

---

## 📄 Licence

Ce projet est sous licence **GNU General Public License v3.0 (GPLv3)**. Les outils tiers téléchargés restent soumis à leurs licences respectives.

## Lecteur vidéo séparé (`--player`)

Lancer `start_add_dub.bat --player` depuis les sources, ou `add_dub.exe --player` dans une distribution recompilée. Pour ouvrir directement un fichier : `add_dub.exe --player -i "C:\Videos\film.mkv"`.

Ce mode utilise mpv embarqué dans `tools/mpv`. Il lit la vidéo originale et les deux WAV préparés (voix TTS et audio original atténué), sans fabriquer de nouvelle vidéo. Le mode `--gui` conserve son fonctionnement d'export et son aperçu mpv.

Le clic droit donne accès aux pistes audio, aux sous-titres et à « Vocaliser les sous-titres ». Le lecteur choisit les sous-titres selon la langue système lorsqu'une piste correspondante est disponible. La vocalisation utilise la piste sélectionnée et les fonctions existantes d'add_dub : extraction SRT, génération TTS, extraction audio et ducking.

La fenêtre de vocalisation permet de choisir moteur, langue, région, voix, atténuation en dB, vitesses TTS minimale/maximale et niveaux TTS/BG (1 = normal, 0 = muet). « Enregistrer les réglages » les conserve dans `player-data/settings.json`. Ctrl+Maj+D lance directement la préparation avec ces réglages : pause, fenêtre de traitement, fermeture après réussite et lecture depuis le début. En lancement manuel, « Rejouer » et « Continuer » restent proposés.

Les WAV sont conservés dans `player-data/wav/`, les travaux temporaires sont isolés dans `tmp/player/`. Les réglages du lecteur ne modifient pas `options.conf`. Aucune réutilisation automatique des WAV comme cache n'est encore implémentée. Les sous-titres externes ouverts dans mpv ne sont pas encore raccordés à la vocalisation.

L'adaptateur mpv partagé avec l'aperçu du GUI est dans `add_dub/adapters/mpv.py`. La préparation centralisée dans `scripts/prepare_tools.py` appelle `scripts/prepare_mpv.py` pour sa DLL.

Le code spécifique est regroupé dans `add_dub/player/` (interface, commandes, préparation et fichiers). Les moteurs TTS et le ducking restent ceux de `add_dub/core/`, et le sélecteur vocal est celui du GUI.

## Interface de production (`--gui`)

> **Le mode `--gui` est en chantier.** Il est disponible pour les essais, mais des bugs peuvent subsister et son interface comme ses fonctionnalités peuvent encore évoluer. Il ne constitue pas encore une version finalisée. Le mode console interactif reste le mode par défaut.

Le code de l’interface est regroupé dans `add_dub/gui/` : `application.py`
(fenêtre principale), `dialog.py` (configuration), `widgets.py`, `theme.py`,
`titlebar.py`, `model.py` et `run.py`. Le point d’entrée `main` du paquet charge
Qt uniquement pour le mode graphique. Les ressources restent dans `docs/`.

Le lancement sans argument conserve l’assistant console interactif. Pour ouvrir la fenêtre :

```cmd
add_dub.exe --gui
```

Depuis les sources :

```cmd
start_add_dub.bat --gui
```

Utilisez le menu **Ouvrir** pour choisir des vidéos ou un dossier et ouvrir la fenêtre de configuration. Le bouton **Paramètres** est réservé aux futures options globales et reste désactivé. Les sous-dossiers sont toujours inclus en mode GUI. La liste de gauche permet de sélectionner les fichiers ; pendant leur analyse, une barre de progression affiche le nombre de vidéos vérifiées sur le total (par exemple 17/125). Les vidéos sans sous-titres détectés sont signalées et ne peuvent pas être sélectionnées. Choisissez parmi les pistes audio et les sous-titres détectés, puis sélectionnez le moteur vocal, la langue, la régionalisation et la voix. La traduction et les réglages audio sont également configurables.

Les réglages communs sont initialisés à partir de la première vidéo admissible du lot. Sélectionner une autre vidéo permet de personnaliser ses réglages sans modifier ceux des autres fichiers. Ajoutez ensuite les vidéos à la file d’attente : chacune apparaît avec son nom de fichier, le nom de son dossier de destination et son statut. Les chemins complets sont disponibles au survol. Le menu du clic droit permet de les afficher dans les colonnes, d’arrêter le traitement, de retirer un fichier, de retirer les entrées terminées ou de vider la liste. Les retraits sont disponibles à l’arrêt et ne suppriment aucun fichier sur disque. Le bouton **Démarrer** lance la file.

En mode GUI, l’arborescence des dossiers est automatiquement conservée en sortie, y compris le nom du dossier ajouté. Les options du lot permettent de choisir entre reprendre en ignorant les sorties existantes et les remplacer.

Les réglages sont initialisés depuis `options.conf` et les arguments CLI, par exemple `add_dub.exe --gui -i "C:\Videos" --tts-engine edge`. Les modifications restent propres aux lots de la session et ne réécrivent pas `options.conf`. La colonne Statut indique les étapes et les erreurs ; les détails des erreurs sont accessibles en survolant leur statut. Le bouton vert lance le traitement, puis devient rouge pour interrompre immédiatement la vidéo en cours. L’arrêt termine le batch et ses processus enfants, puis supprime les fichiers temporaires de cette vidéo et son mixage provisoire. La vidéo reste en attente pour être reprise depuis le début. Une sortie précédente reste intacte : le nouveau mixage ne la remplace qu’après réussite. Il est grisé lorsque la liste est vide, qu’aucune vidéo ne reste à traiter ou qu’un arrêt est déjà demandé.

La file est séparée en deux parties : **En attente** et **Terminé**. Chaque vidéo réussie passe immédiatement dans la seconde ; la vidéo en cours reste en tête de la première. Les lignes sont mises à jour sans reconstruire les listes à chaque vidéo. Les colonnes sont redimensionnables et leurs largeurs sont synchronisées entre les deux listes. Les onglets **En attente** et **Terminé**, avec leurs compteurs, permettent de basculer entre les deux listes ; une seule est affichée à la fois.

Les barres vertes indiquent une progression estimée. Les étapes audio, synthèse vocale, ducking et mixage ont des poids relatifs de 19, 50, 10 et 20 ; l’extraction des sous-titres ajoute 1, l’OCR et la traduction 30 chacun lorsqu’ils sont nécessaires. Les poids sont normalisés sur 100 %. Le ducking et l’OCR sans progression détaillée avancent à la transition vers l’étape suivante. Une traduction réutilisée ou évitée ne conserve pas son poids.

La progression globale, affichée à 0,1 %, attribue une part égale à chaque vidéo restante au lancement. Après un arrêt, la barre revient à zéro ; le prochain lancement repart à zéro pour les seules vidéos restantes. Les sorties déjà présentes sont vérifiées par dossier avant de lancer les processus vidéo et sont exclues des durées utilisées pour l’estimation. Le temps écoulé est affiché à côté ; le temps restant estimé apparaît après la première vidéo réellement traitée et est recalculé avec la moyenne des durées observées, hors simulations. Des vidéos de durées différentes peuvent rendre cette estimation moins précise. Les deux listes utilisent un défilement au pixel, animé à la molette et compatible avec le défilement tactile.

### Compilation Windows

Les icônes de l’interface utilisent des SVG de la collection Icons8 Skeuomorphism. Les sources et les conditions d’attribution sont indiquées dans [docs/icons8/README.md](docs/icons8/README.md).

Après préparation de l’environnement avec `start_add_dub.bat`, lancez `compil.bat`. Le script s’arrête avec un code d’erreur si la compilation ou la copie échoue. Distribuez **tout le dossier `dist\add_dub`**, qui contient l’EXE, les bibliothèques Python/Qt et les outils portables. Le même EXE propose la console par défaut et la fenêtre avec `--gui`.

Le cadre architectural et les limites repérées sont détaillés dans [AUDIT.md](AUDIT.md).

La fenêtre utilise PySide6/Qt et reste compatible avec l’agrandissement Windows et la Loupe. La dépendance est installée dans la venv du projet, créée avec le Python de `tools`.
