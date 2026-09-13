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

Le lecteur charge exclusivement `tools/vlc/libvlc.dll` et les modules livrés à
côté. Aucune recherche dans Program Files ou le registre. Le lancement de
développement `start_add_dub.bat --gui` prépare le moteur si nécessaire ;
`compil.bat` le copie dans la distribution, qui fonctionne sans téléchargement
ni installation de VLC chez l’utilisateur.

Version : VLC 3.0.23 Windows x64, distribution officielle VideoLAN.
Source : https://download.videolan.org/pub/videolan/vlc/3.0.23/
Le script `scripts/prepare_vlc.py` vérifie le SHA-256 officiel de l’archive.
Les fichiers COPYING, AUTHORS et THANKS accompagnent le moteur.
Le code source correspondant est disponible dans ce même répertoire officiel.
