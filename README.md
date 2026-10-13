# add_dub — écouter les sous-titres de ses vidéos

add_dub transforme les sous-titres en **voix synchronisée**, atténue le son
d’origine pendant les répliques et produit un MKV. Il vise l’accessibilité et
le confort d’écoute : la voix originale reste en fond, sans clonage vocal.
Le traitement utilise le CPU, sans carte graphique dédiée.

[Manuel](https://jobijoba2000.github.io/add_dub/) ·
[Guide du code actuel](docs/usage.md) ·
[Licences et composants tiers](THIRD_PARTY_NOTICES.md) ·
[Préparation de la v2](docs/release-v2.md)

> **Version 2.0.0 : interface graphique, lecteur et assistant console.**
> [Télécharger la dernière release Windows x64](https://github.com/Jobijoba2000/add_dub/releases/latest).

## Choisir son mode

| Mode du code actuel | Lancement depuis les sources | Résultat |
|---|---|---|
| Assistant console | `start_add_dub.bat --interactive` ou sans argument | Choix guidés et export MKV |
| Interface de production | `start_add_dub.bat --gui` | Configuration par vidéo, aperçu, file d’attente, export MKV |
| Lecteur | `start_add_dub.bat --player` | Lecture mpv et vocalisation avec deux WAV, sans export MKV |
| Automatisation | `start_add_dub.bat --batch -i "C:\Videos\film.mkv"` | Traitement sans questions |

La distribution v2 partage ses outils et dépendances entre trois lanceurs :

- **`add_dub.exe`** ouvre le GUI par défaut.
- **`add_dub_console.exe`** ouvre l’assistant et fournit la CLI/batch.
- **`add_dub_player.exe`** ouvre le lecteur.

Chacun possède son icône. Les flags explicites restent disponibles ;
`--version` affiche la version. Depuis les sources, le lancement sans argument
conserve l’assistant console.

## Première utilisation

**Avec la v1 portable :** décompressez l’archive, ajoutez une vidéo dans
`input/`, puis double-cliquez sur `add_dub.exe`. Choisissez la piste audio,
les sous-titres et la voix dans l’assistant. Les exports vont dans `output/`.

**Avec le code actuel :**

```cmd
git clone https://github.com/Jobijoba2000/add_dub.git
cd add_dub
start_add_dub.bat --gui
```

Le lanceur prépare Python, l’environnement virtuel et les outils portables.
Les premières préparations nécessitent Internet. Il vérifie Visual C++ x64
et peut lancer son installeur officiel, avec une demande administrateur Windows.
Subtitle Edit nécessite .NET Framework 4.8. Les composants standards ciblent
Windows 10/11 x64.

Dans le GUI, ouvrez des vidéos ou un dossier, choisissez les pistes et la voix,
utilisez l’aperçu pour régler les niveaux, puis ajoutez le lot à la file et
cliquez sur **Démarrer**. Les sous-dossiers sont inclus. Les réglages peuvent
être adaptés par vidéo ; l’arborescence est conservée en sortie.

## Moteurs vocaux et traduction

| Moteur | Connexion | Voix |
|---|---|---|
| OneCore | Synthèse locale | Voix installées dans Windows |
| Edge TTS | Internet à chaque synthèse | Catalogue de voix Microsoft en ligne |
| gTTS | Internet à chaque synthèse | Voix Google par langue |

Edge et gTTS envoient le texte des sous-titres à leur service. OneCore utilise
les voix installées dans Windows et effectue la synthèse sur le PC.

La traduction propose **CTranslate2** (modèles locaux Opus-MT, pivot anglais,
NLLB) et **Google Traduction** (en ligne). CTranslate2 télécharge ses modèles
à la première utilisation ; son choix ne provoque pas de secours Google.
Google peut se replier sur les modèles locaux. Certaines paires exigent NLLB
ou l’ajout d’une révision de modèle dans `models.lock.json`.
Le modèle NLLB d’origine comporte une restriction d’usage commercial.

```cmd
start_add_dub.bat --batch -i "C:\Videos\film.mkv" --tts-engine edge --voice fr-FR-DeniseNeural
start_add_dub.bat --batch -i "C:\Videos\Series" --recursive --preserve-tree --skip-existing
start_add_dub.bat --batch -i "C:\Videos\film.mkv" --translate --translate-from en --translate-to fr --translation-engine ctranslate2
start_add_dub.bat --batch -i "C:\Videos\film.mkv" --offline --tts-engine onecore --no-translate
```

`--offline` interdit les services distants et les téléchargements de modèles.
Une voix ou un modèle local manquant doit être préparé auparavant.

## Entrées, sorties et conservation des fichiers

Les MKV acceptent les sous-titres texte ASS/SSA, SRT et WebVTT, ainsi que PGS
et VobSub via OCR. Pour les MP4/AVI, fournissez un SRT portant le même nom à
côté de la vidéo. Un SRT peut aussi être fourni dans `srt/`.

L’export contient la vidéo copiée (AVI : transcodage), le mix voix + fond
atténué par défaut, l’audio source **réencodé en stéréo** au codec choisi et
les sous-titres. Les pistes ont leurs langues dans le code actuel. Les vidéos
d’entrée ne sont pas modifiées. Les exports du code actuel sont publiés après
réussite du muxage ; une interruption conserve une sortie précédente.

La sélection d’un sous-titre intégré crée une copie persistante dans `srt/`.
Les fichiers homonymes de dossiers différents et la réutilisation des
traductions restent des points à valider avant la v2.

## Réglages et langues de l’interface

`options.conf` fixe les valeurs par défaut. Dans la console, le suffixe `d`
demande le réglage au lancement : `tts_engine = onecore d`.
Le bouton **Paramètres** du GUI édite ce fichier en conservant commentaires
et options inconnues. Les réglages d’un lot n’écrasent pas ces préférences.
Le lecteur conserve ses réglages séparément dans `player-data/settings.json`.

La console et les messages traduits proposent **français, anglais, espagnol,
allemand et italien**, selon `language = auto` ou un code explicite.
Les commandes, explications et messages d’état du GUI et du player sont
disponibles dans ces cinq langues.
Redémarrez après un changement de langue. La traduction des sous-titres,
la langue des voix et la langue de l’interface sont des choix différents.

## Développement et vérification

```cmd
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe -m pip check
.venv\Scripts\python.exe scripts\audit_i18n.py
compil.bat
compil.bat --zip --tag v2.0.0
```

Sans option, `compil.bat` prépare le dossier portable. `--zip` crée aussi
l’archive Windows dans `dist/` ; `--tag v2.0.0` la nomme
`add_dub_v2.0.0_win64.zip`. Un tag comme `v2.0.0-rc1` permet de nommer un essai.
Sans `--tag`, le nom utilise la version actuelle du projet. Le tag sert au nom
de l’archive ; la version des EXE reste celle définie dans le projet.
`compil.bat --help` affiche les options sans compiler.

La compilation produit `dist/add_dub/`, avec ses outils, accès à la documentation,
notices trouvées et inventaire `THIRD_PARTY.json`. Les EXE/DLL/PYD de tout
le dossier sont empreintés, y compris Qt et CTranslate2 sous `_internal`.
La vidéo d’exemple de la v1 est fournie dans `input/extrait.mkv` pour un premier
essai. Les autres vidéos, caches et données personnelles sont exclus du ZIP.
Le dossier `docs/` de la distribution contient uniquement `documentation.html`,
avec un bouton vers le manuel en ligne. Le manuel complet et les fichiers des
icônes ne sont pas copiés dans ce dossier ; les ressources de l’application
sont embarquées sous `_internal/assets/icons/`. Dans le projet, ces icônes
sont dans `assets/icons/` ; `docs/assets/` contient uniquement les images du site.

[Résultats de comparaison v1/code actuel](docs/release-v2.md),
[guide détaillé](docs/usage.md), [aperçu vidéo](docs/preview.md),
[revue des dépendances](docs/security-review.md).

## Licence

Le projet est sous **GNU GPLv3**, voir [LICENSE](LICENSE).
Les composants et modèles tiers conservent leurs propres conditions.
Le bouton **À propos et licences** du GUI et le menu du player affichent
les notices livrées et la licence du projet.
Les questions de redistribution encore ouvertes, notamment pour mpv
et les notices Qt, sont exposées dans
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
