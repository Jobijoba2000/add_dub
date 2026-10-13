# Manuel d’add_dub v2

Ce guide accompagne les sources actuelles et la distribution Windows v2.
La commande `start_add_dub.bat` prépare les dépendances et transmet ses arguments.
Dans la distribution v2, `add_dub.exe` ouvre le GUI, `add_dub_player.exe`
ouvre le lecteur et `add_dub_console.exe` ouvre l’assistant. Pour les commandes
batch de ce guide, remplacez `start_add_dub.bat` par `add_dub_console.exe`.
La distribution fournit `input/extrait.mkv`, l’exemple de la première release,
pour essayer le GUI, le lecteur ou le traitement console.

## Produire un MKV avec le GUI

Lancez `start_add_dub.bat --gui`. **Ouvrir** permet d’ajouter des vidéos ou un
dossier, avec ses sous-dossiers. La configuration détecte les pistes et indique
les fichiers sans sous-titres utilisables. Les réglages communs partent de la
première vidéo admissible ; sélectionner une autre vidéo permet de les adapter.

Choisissez la piste audio à atténuer et le sous-titre à vocaliser. Une piste
« Signs/Songs » ou forcée ne contient généralement pas les dialogues complets.
Vérifiez la piste sélectionnée, même si sa langue semble correcte.
Choisissez ensuite moteur, langue, région et voix. Une voix française ne
traduit pas un sous-titre anglais : activez la traduction séparément.

L’onglet **Essai** produit un extrait doublé à partir des réglages de la vidéo.
La plage est en mm:ss ; les coupes vidéo dépendent des images clés.
Voir [les détails de l’aperçu](preview.md). Réglez le fond et la voix, ajoutez
le lot puis démarrez la file. L’arborescence de sortie inclut le nom du dossier
ajouté. Choisissez d’ignorer les sorties existantes ou de les remplacer.

La file sépare **En attente** et **Terminé**. Le clic droit permet de consulter
les chemins, arrêter, retirer des entrées ou vider la liste ; retirer une entrée
ne supprime pas un fichier sur disque. L’arrêt interrompt la vidéo en cours
et nettoie ses temporaires. Elle reste en attente et reprend depuis le début.
Une sortie précédente est remplacée uniquement après réussite.

Les pourcentages d’étape sont mesurés lorsqu’un moteur les fournit. Le total
est une estimation pondérée des étapes, et non une estimation exacte du temps.
Une étape sans mesure affiche « en cours ». L’estimation du temps restant
apparaît après une vidéo réellement traitée ; des durées différentes la rendent
moins précise.

## Lire et vocaliser sans exporter

```cmd
start_add_dub.bat --player -i "C:\Videos\film.mkv"
```

Le player utilise la DLL mpv fournie dans `tools/mpv`. Ouvrez une vidéo avec
Ctrl+O. Espace met en pause, les flèches déplacent de cinq secondes, M coupe
le son, F bascule le plein écran et Échap en sort. Le clic droit choisit pistes
audio et sous-titres, puis **Vocaliser les sous-titres** prépare la voix.
Le lecteur sélectionne les sous-titres selon la langue système si une piste
correspondante existe. Vérifiez ce choix avant la vocalisation.

La fenêtre vocale règle moteur, langue, région, voix, atténuation, vitesse
minimale/maximale et volumes BG/TTS. 1 signifie le niveau normal et 0 le silence.
**Enregistrer les réglages** les conserve dans `player-data/settings.json`.
Ctrl+Maj+D lance directement la préparation avec ces réglages : la vidéo passe
en pause, le traitement s’affiche, puis la lecture recommence après réussite.
En lancement manuel, **Rejouer** ou **Continuer** choisit la reprise.

Le lecteur prépare deux WAV : voix TTS et audio d’origine atténué. Ils restent
dans `player-data/wav/`. Les temporaires sont isolés dans `tmp/player/`.
Les réglages du lecteur ne modifient pas `options.conf`. Il n’existe pas encore
de réutilisation automatique des WAV ni de vocalisation raccordée aux
sous-titres externes ouverts directement dans mpv. Le player ne propose pas
actuellement les réglages de traduction du GUI de production.

## Assistant et batch

Sans argument ou avec `--interactive`, l’assistant console guide le choix des
vidéos, pistes et paramètres. Il applique la configuration du premier fichier
aux suivants. Il ne parcourt pas automatiquement les sous-dossiers.

```cmd
start_add_dub.bat --batch -i "C:\Videos\film.mkv" --tts-engine onecore --no-translate
start_add_dub.bat --batch -i "C:\Videos\Series" --recursive --preserve-tree --skip-existing
start_add_dub.bat --batch -i "film.mkv" --tts-engine edge --voice fr-FR-DeniseNeural --bg-mix 0.8 --tts-mix 1.2 --ducking-db -5
```

`--audio-index` est l’index global FFmpeg de l’audio, visible avec FFprobe.
`--sub mkv:N` choisit le **numéro parmi les pistes de sous-titres**, à partir de
zéro ; `--sub stream:N` utilise l’index global FFmpeg. Ces nombres ne sont pas
interchangeables. Pour le fichier Naruto utilisé lors de l’audit : audio japonais
à l’index 1, français à 2 ; ASS à `mkv:0`, PGS complet à `mkv:1`, PGS
signes/chansons à `mkv:2`. Ces index dépendent du fichier.

`--sub srt` choisit un SRT ; un fichier homonyme dans `srt/` peut prendre la
priorité sur le sidecar. `auto` recherche le sidecar, puis la première piste
intégrée. Avec des épisodes homonymes dans plusieurs dossiers, vérifiez les
copies persistantes et les traductions réutilisées.

`--limit-duration-sec 180` limite l’essai aux trois premières minutes.
Le code actuel coupe aussi les répliques qui chevauchent la fin, avant leur
traduction et vocalisation. La vidéo copiée et ses timestamps peuvent conserver
une légère marge liée aux paquets et images clés ; cette commande ne garantit
pas une coupe à l’image près. Dans la v1 publiée, le muxage garde toute la durée
vidéo malgré la limite de traitement.

## Traduire les sous-titres

```cmd
start_add_dub.bat --batch -i "film.mkv" --translate --translate-from en --translate-to fr --translation-engine ctranslate2 --tts-engine onecore
```

La source peut être forcée ou détectée avec `auto`. Un sous-titre déjà dans
la langue cible est conservé. Le moteur CTranslate2 cherche un modèle bilingue,
puis un pivot anglais et NLLB. Les modèles nécessaires sont téléchargés à la
première utilisation, aux révisions de `models.lock.json`. Leur synthèse et
traduction s’exécutent ensuite localement. Le cache de traduction se situe
dans `%USERPROFILE%/.cache/add_dub/ct2_models`.

Google Traduction envoie le texte sur Internet et peut se replier sur les
modèles CTranslate2. Choisir CTranslate2 n’autorise pas un secours Google.
`--offline` interdit téléchargements et services distants, exige OneCore
et nécessite que les modèles de traduction soient déjà prêts.
Si la traduction échoue, le pipeline peut poursuivre avec les sous-titres
originaux : consulter le journal et vérifier le SRT produit avant de considérer
la traduction réussie.

Les modèles ont leurs propres licences. NLLB-200 d’origine est sous
CC-BY-NC-4.0 ; voir les [notices des composants](../THIRD_PARTY_NOTICES.md).

## Préférences et dépannage

`options.conf` est recherché à côté de l’exécutable compilé, ou selon
`ADD_DUB_OPTIONS`. `options.example.conf` fournit un point de départ.
Les arguments CLI prennent la priorité sur les préférences ; celles-ci prennent
la priorité sur les valeurs internes. Le suffixe `d` déclenche une question dans
l’assistant. Le GUI permet d’éditer les préférences avec **Paramètres** ; les
paramètres propres à chaque lot et ceux du player restent indépendants.

- **Erreur CTranslate2/DLL :** installer ou réparer le runtime
  [Visual C++ x64 officiel](https://aka.ms/vc14/vc_redist.x64.exe).
  Si l’installateur demande un redémarrage, l’effectuer avant de relancer.
- **Edge/gTTS indisponible :** consulter l’erreur réseau, puis essayer OneCore.
  Ces services peuvent changer ; un cache de catalogue ne garantit pas la synthèse.
- **PGS non reconnu :** vérifier .NET 4.8, Subtitle Edit, les données Tesseract
  de la bonne langue et la piste choisie. L’OCR peut introduire des erreurs.
- **Doublage dans la mauvaise langue :** contrôler sous-titres, traduction et
  voix séparément, ainsi que les anciens SRT présents dans `srt/`.

Les journaux conservent des chemins et peuvent contenir le texte traité ; les
relire avant de les partager. Ne pas joindre de vidéos personnelles à un
rapport public.
