# Audit du projet et cadre de l’interface graphique

## Philosophie retenue

add_dub est un outil Windows portable d’accessibilité et de confort d’écoute : il transforme des sous-titres en voix synchronisée, conserve la vidéo et l’audio original, et produit un MKV avec un mix atténué. Le traitement fonctionne sur CPU, avec OneCore hors ligne ou des moteurs connectés. La traduction est optionnelle et le traitement par lot fait partie du fonctionnement central.

Les conventions à conserver : options.conf avant les valeurs par défaut, assistant console sans argument, séparation entre CLI, configuration, pipeline et adaptateurs externes, outils dans tools/, sorties et temporaires séparés des vidéos sources. La fenêtre ne réécrit pas les préférences.

## État et architecture

Le mode --gui est en chantier. Son interface et ses fonctionnalités peuvent évoluer ; il n’est pas considéré comme finalisé.

- PySide6/Qt fournit les contrôles graphiques. La venv utilise le Python portable de tools/. Aucun serveur web local n’est nécessaire.
- Les modes console interactif, batch et GUI sont mutuellement exclusifs. La fenêtre principale démarre maximisée et conserve la barre des tâches Windows.
- La configuration détecte les fichiers, les pistes et les voix en arrière-plan. Le choix vocal suit moteur, langue, régionalisation et voix.
- Les réglages communs sont adaptés à la première vidéo admissible. Chaque vidéo peut recevoir des réglages personnalisés.
- Les lots configurés sont ajoutés à une liste d’attente modifiable. La fenêtre lance le batch existant dans un processus séparé avec une liste d’arguments, sans shell.
- La progression porte sur les fichiers traités. Le journal affiche les sorties du processus. L’arrêt interrompt le batch et ses enfants. Chaque vidéo GUI dispose de temporaires isolés et d’un mixage provisoire, nettoyés après interruption ; la sortie finale est publiée uniquement après réussite.
- L’interface est en français ; les messages du moteur conservent la langue configurée.

## Corrections associées

- Transmission du moteur de traduction et du débit audio au batch ; prise en charge explicite de --no-translate.
- Protection de l’annulation de la configuration console.
- Recherche de options.conf près de l’exécutable compilé, sauf surcharge explicite.
- Extraction des sous-titres intégrés hors MKV via FFmpeg et copie des SRT externes dans le dossier de travail.
- Compilation avec arrêt sur erreur et inclusion de Qt par les hooks PyInstaller. Les anciens scripts Tcl/Tk ne sont plus utilisés.

## Vérification avant commit

La suite tests/test_gui.py couvre le choix des modes, le dispatch, les options transmises au batch, les valeurs invalides, la commande du mode compilé et la construction, l’ouverture et la fermeture de la configuration d’un dossier vide. Ce dernier test utilise Qt hors écran, sans synthèse vocale ni réseau.

Commande depuis la racine :

    .venv\Scripts\python.exe -m unittest discover -s tests -v

Les essais manuels de la Loupe ont guidé le choix de Qt. Un test hors écran ne valide pas la lecture par la Loupe ni l’affichage sur toutes les résolutions. La compilation Qt avait été vérifiée pendant le développement ; aucune nouvelle compilation n’est prévue pour ce nettoyage. Les services vocaux et les modèles de traduction ne sont pas couverts de bout en bout par cette suite.

## Points restant à surveiller

- Certains chemins du pipeline utilisent encore les helpers console ; l’interface réutilise le batch plutôt que de refondre le pipeline.
- La sélection automatique des SRT et les collisions de noms entre dossiers méritent des essais supplémentaires, notamment pour les sous-titres temporaires.
- Certains codecs acceptés par la CLI peuvent retomber sur AAC ; vérifier les arguments effectifs avant d’élargir les choix graphiques.
- Certaines erreurs de traduction entraînent un repli sur les sous-titres originaux : le journal doit être consulté.

Cet audit décrit le périmètre du développement GUI et ses limites, pas une validation exhaustive de tous les moteurs et scénarios.
