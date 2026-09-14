# Essai vidéo

L’onglet Essai utilise la vidéo sélectionnée dans la liste (ou la référence du
dossier sélectionné). La plage est exprimée en mm:ss et ne modifie pas les
réglages du lot. Les clics gauche/droit fixent le début/la fin.

Chaque essai utilise les réglages applicables à cette vidéo et un répertoire
`tmp/gui-preview-*`. Les flux de l’extrait sont copiés sans réencodage pour accélérer la préparation.
La coupe dépend des images clés du flux source et ne garantit pas une précision
à l’image près. Extraction et doublage ont chacun leur pourcentage.
Les sous-titres sont copiés, décalés et coupés avant traduction et synthèse vocale.
La fermeture de la fenêtre ou le remplacement de l’essai nettoie ses fichiers.

Le lecteur charge exclusivement `tools/mpv/libmpv-2.dll`, avec le même adaptateur
que `--player` (`add_dub/adapters/mpv.py`). Aucun VLC ni installation personnelle
de mpv n'est utilisé. L'aperçu continue de lire le MKV de test produit par le
pipeline existant ; les fonctions de fabrication du doublage ne changent pas.

`start_add_dub.bat` prépare les outils via `scripts/prepare_tools.py`, qui appelle
la préparation de mpv si nécessaire, avant de lancer le mode demandé.
`scripts/prepare_mpv.py` télécharge une version fixe, contrôle le SHA-256 de
l'archive et de la DLL, puis extrait uniquement la DLL avec le tar fourni par
Windows. `compil.bat` la copie dans la distribution : l'utilisateur du logiciel
compilé n'a rien à télécharger ni à installer séparément.

Version Windows x64 : `20260903-git-69e63f425a`, build shinchiro référencé sur
https://mpv.io/installation/ . Archive et sources de construction :
https://github.com/shinchiro/mpv-winbuild-cmake/releases/tag/20260903 .
Les empreintes figées sont dans `scripts/prepare_mpv.py`.
