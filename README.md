# add_dub — doublage TTS à partir de sous-titres (Windows)

`add_dub` permet de générer automatiquement une voix TTS synchronisée à partir de sous-titres, d’atténuer le son d’origine pendant les répliques (ducking), puis de remuxer le tout dans un **fichier MKV** avec :
- Piste 0 : mix TTS + audio original
- Piste 1 : audio original seul
- Sous-titres conservés

Fonctionne uniquement sous **Windows** (TTS OneCore via `winrt`). Tout est traité en local.

---

## Installation

### Télécharger la release
Téléchargez la version portable :  
[📥 add_dub_v0.3.0_win64.zip](https://github.com/Jobijoba2000/add_dub/releases/download/v0.3.0/add_dub_v0.3.0_win64.zip)

Dézippez, puis lancez :

```
start_add_dub.bat
```

Le script :
- Télécharge et installe la Toolbox (Python portable, ffmpeg, MKVToolNix, Subtitle Edit)
- Crée les dossiers nécessaires (`input`, `output`, `tmp`)
- Configure automatiquement l’environnement Python
- Lance l’outil

### Git clone (optionnel)

```
git clone https://github.com/jobijoba2000/add_dub.git
cd add_dub
start_add_dub.bat
```

---

## Utilisation

### Mode interactif (par défaut)
Il suffit de lancer :
```
start_add_dub.bat
```
L’outil posera les questions nécessaires (voix TTS, ducking, mix, offsets, etc.) puis produira un MKV final.

### Mode batch
Pour automatiser le traitement sans questions :
```
start_add_dub.bat --batch
```
Pour afficher l’aide :
```
start_add_dub.bat -h
```

---

## Formats pris en charge
- Entrée **MKV** (SRT ou pistes sous-titres intégrées). OCR automatique pour PGS via Subtitle Edit.
- Entrée **MP4** avec **SRT sidecar obligatoire**.

---

## Fichier de configuration

Lors de la première exécution, `options.conf` est créé à partir de `options.example.conf`.

Dans ce fichier :
- Les paramètres définissent les valeurs par défaut utilisées en batch et en interactif.
- Si un paramètre contient la lettre **`d`** à la fin de sa ligne, cela signifie **display** : la valeur sera **demandée à l’utilisateur** en mode interactif.
- Sans `d`, la valeur est directement utilisée.

Exemple :
```
ducking_db = -5.0 d
bg = 1.0
```
→ Ici `ducking_db` sera demandé en interactif, `bg` non.

---

## Sortie

- Un fichier MKV avec deux pistes audio et les sous-titres
- Tous les fichiers traités sont placés dans `output/`

---

## Commandes utiles

```
start_add_dub.bat --batch              # traitement sans interaction
start_add_dub.bat -h                   # aide et options
```

---

## Licence

Code sous licence **MIT**, dépendances incluses dans la Toolbox.
