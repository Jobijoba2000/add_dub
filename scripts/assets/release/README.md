# Vidéo d’exemple de la distribution

`extrait.mkv` est le fichier livré dans `input/` avec la release v1.0.0,
récupéré dans l’archive officielle `add_dub_v1.0.0_win64.zip`.

SHA-256 : `20ad13f80d4ab1bb83e606b2ef3cadc6fbecd48dd31703f12baa13fa3b7757e5`.

`compil.bat` appelle `scripts/package_release.py`, qui le copie dans
`dist/add_dub/input/extrait.mkv`. La création du ZIP conserve cet exemple
et exclut les autres vidéos du dossier `input/`.

`documentation.html` reprend la page de la v1 : un bouton ouvre le manuel
sur GitHub Pages. C’est le seul fichier du dossier `docs/` livré aux utilisateurs.
`README-WINDOWS.md` devient le `README.md` de la distribution portable.

`compil.bat --zip --tag v2.0.0` compile, prépare ce contenu puis crée
`dist/add_dub_v2.0.0_win64.zip`. Sans `--zip`, le dossier seul est préparé.
