# Préparer la release v2.0.0

La v2 reprend le doublage de la v1 et ajoute surtout les interfaces graphiques,
le lecteur et une distribution plus simple à ouvrir.
Le texte destiné à GitHub est dans [release-notes-v2.md](release-notes-v2.md).
Les changements sont également dans [CHANGELOG.md](../CHANGELOG.md).

## Trois lanceurs dans une même distribution

| Exécutable | Ouverture par défaut |
|---|---|
| `add_dub.exe` | Interface graphique de production |
| `add_dub_console.exe` | Assistant interactif ; CLI et batch |
| `add_dub_player.exe` | Lecteur avec vocalisation des sous-titres |

Ils partagent `_internal/`, `tools/`, les préférences et la documentation.
Chaque lanceur possède son icône. Les flags explicites restent disponibles,
et `--version` affiche 2.0.0. Depuis les sources, le lancement sans argument
conserve l’assistant ; `--gui` et `--player` ouvrent leurs interfaces respectives.

Les fenêtres utilisent le lanceur console pour les traitements enfants,
afin de conserver les journaux et la progression. La version est aussi
inscrite dans les propriétés Windows des exécutables.

## Principaux changements depuis la v1

- GUI de production : configuration par vidéo, aperçu, file d’attente,
  arrêt et reprise du traitement.
- Player mpv : lecture, pistes audio et sous-titres, vocalisation avec deux WAV,
  réglages enregistrés et raccourci Ctrl+Maj+D.
- Éditeur des préférences, progression détaillée et métadonnées des pistes.
- Corrections du mixage, de la gestion des processus et des sorties interrompues.
- Barres du player sans padding intérieur et à angles droits.
- Interface traduite dans les cinq langues, avec les commandes, explications,
  erreurs et messages d’état du GUI et du player. Un changement de langue
  s’applique partout après redémarrage.
- README et manuel réorganisés, version et licences visibles depuis le GUI
  et le player, notices livrées et inventaire des binaires.

## Référence v1 et essais utiles

L’archive officielle v1.0.0 a été téléchargée et utilisée avec Naruto pour
retrouver son comportement de base. Les essais ont produit des exports avec
OneCore, Edge TTS et gTTS. L’extraction ASS, l’OCR PGS et la traduction ont
également été exercés. Les essais du code actuel couvrent ces moteurs
et la traduction Google/CTranslate2.

Cela confirme les principales différences utiles aux notes de release :
la v1 fonctionne avec assistant/batch ; le code actuel ajoute GUI/player,
langues des pistes et gestion plus robuste des traitements.
La limite d’un extrait conserve toute la vidéo en v1 ; le code actuel limite
le muxage et coupe maintenant les sous-titres qui chevauchent la fin.

Les journaux détaillés restent dans `tmp/release-audit/`. Ils servent de
référence locale et ne font pas partie de la distribution.

La suite du projet compte **148 tests réussis** après les changements de langue
et des lanceurs. Pour la compilation, la vérification reste courte : lancement,
aide/version et petit doublage OneCore avec les outils embarqués.

## Fichiers de release

`compil.bat` produit `dist/add_dub/`, avec les trois EXE, outils, documentation,
licence du projet, notices tierces et `THIRD_PARTY.json`. Ce dernier inventorie
les EXE/DLL/PYD, y compris ceux de `_internal`, et les notices trouvées.
Le dossier `input/` contient `extrait.mkv`, la vidéo d’exemple de la v1,
copiée depuis `scripts/assets/release/`.
Le dossier `docs/` contient uniquement `documentation.html`, avec un bouton
vers le manuel en ligne, comme dans la v1. Le README portable présente les
lanceurs et ce lien. Dans le projet, le manuel reste dans `docs/` et les icônes
dans `assets/icons/`. La compilation embarque les ressources nécessaires sous
`_internal/assets/icons/`.

L’archive doit contenir ce dossier portable et son exemple `input/extrait.mkv`,
sans les autres vidéos d’essai, sorties,
préférences personnelles et caches de modèles. Les versions Python et modèles
sont conservées dans les fichiers de verrouillage livrés.

Pour compiler et créer directement le ZIP Windows :

```bat
compil.bat --zip --tag v2.0.0
```

Le résultat est `dist/add_dub_v2.0.0_win64.zip`. `compil.bat --zip` utilise la
version actuelle du projet ; `--tag v2.0.0-rc1` nomme une archive de test.
Le tag choisit le nom du ZIP ; il ne change pas la version des EXE.
Sans `--zip`, seul le dossier portable est préparé. `compil.bat --help` affiche
l’aide sans compiler. Aucun ZIP de sources n’est créé automatiquement.

Pour zipper un dossier déjà compilé, la commande directe reste disponible :
`.venv\Scripts\python.exe scripts\package_release.py --zip --tag v2.0.0`.
La préparation utilise les réglages OCR fournis dans le dépôt et exclut les
historiques, préférences personnelles et données de travail.

Les conditions particulières à vérifier pour la publication sont centralisées
dans [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md), notamment les licences
des modèles de traduction et les sources/notices des composants natifs.
La compilation locale ne constitue pas une publication de la release.
