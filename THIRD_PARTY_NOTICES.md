# Composants tiers d’add_dub

Le code d’add_dub est sous [GPLv3](LICENSE). Cette licence ne remplace pas les
licences des outils, bibliothèques, modèles ou services. Les notices ci-dessous
décrivent la préparation de la v2 ; elles ne certifient pas encore sa distribution.

## Outils portables

| Composant prévu | Origine/version épinglée | Licence et éléments à livrer |
|---|---|---|
| FFmpeg | Gyan, 8.1.2 full build ; `scripts/prepare_tools.py` | Le `LICENSE` du build local est GPLv3. Fournir ses sources correspondantes, options de compilation et licences de ses dépendances ; ne pas le présenter comme un build LGPL seul. |
| MKVToolNix | 94.0 | GPLv2 ; conserver `tools/MKVToolNix/doc/COPYING.txt` et les licences de ses dépendances avec les sources correspondantes. |
| Subtitle Edit | 4.0.13 | GPLv3 ; conserver `tools/subtitle_edit/LICENSE.txt` et les notices des DLL associées. |
| Tesseract | Archive Tesseract550 du support Subtitle Edit | Apache-2.0 pour le moteur ; contrôler aussi les bibliothèques natives et les modèles téléchargés. La licence complète manque dans l’archive locale examinée. |
| mpv | Build shinchiro `20260903-git-69e63f425a` | Vérifier la licence effective du build et de ses dépendances FFmpeg. La préparation extrait actuellement uniquement `libmpv-2.dll` ; il faut compléter notices et sources avant publication. |
| Python | Runtime portable 3.12, utilisé depuis les sources ; runtime PyInstaller en distribution | PSF et notices des composants embarqués. Le dossier `tools/python` n’est pas copié par `compil.bat`, mais Python est embarqué dans `_internal`. |

Les URL des archives et leurs SHA-256 sont conservés dans les scripts de
préparation. Les empreintes des binaires réellement distribués sont dans
`THIRD_PARTY.json`, produit à la compilation. Les textes présents dans `tools/`
sont aussi regroupés sous `licenses/native/`.

Sources officielles : [FFmpeg](https://ffmpeg.org/legal.html),
[MKVToolNix](https://mkvtoolnix.download/source.html),
[Subtitle Edit](https://github.com/SubtitleEdit/subtitleedit),
[Tesseract](https://github.com/tesseract-ocr/tesseract),
[mpv et sa licence](https://github.com/mpv-player/mpv/blob/master/Copyright),
[construction Windows mpv](https://github.com/shinchiro/mpv-winbuild-cmake/releases/tag/20260903).
Un lien vers la dernière version amont ne remplace pas les sources du build livré.

## Bibliothèques Python et Qt

`requirements.lock.txt` fixe les versions et empreintes des dépendances.
L’inventaire copie les fichiers LICENSE, COPYING et NOTICE trouvés dans
l’environnement de compilation vers `licenses/python/`. Il recense également
les paquets sans texte de licence : un champ « MIT » ou « LGPL » dans les
métadonnées ne remplace pas le texte et les mentions de copyright.

Qt/PySide6 et Shiboken 6.8.2.1 requièrent une attention particulière : les wheels
locaux examinés contiennent un texte de licence commerciale, mais pas tous les
textes GPL/LGPL ni toutes les notices Qt nécessaires. Il faut livrer les textes
applicables, les sources correspondantes et les informations permettant de
remplacer les bibliothèques. Voir les [obligations Qt](https://www.qt.io/development/open-source-lgpl-obligations).

CTranslate2 (MIT) et SentencePiece (Apache-2.0) ne fournissent pas de fichier
de licence détectable dans les wheels locaux examinés. Compléter les notices
depuis les sources de leurs versions exactes, ainsi que celles des bibliothèques
natives qu’ils embarquent.

## Modèles de traduction et OCR

Les modèles sont téléchargés séparément ; leurs droits restent distincts du
moteur CTranslate2. `models.lock.json` fixe les révisions utilisées.

- Les modèles Opus-MT anglais/français : conserver les notices et la provenance
  des modèles d’origine, en plus de celles de la conversion CTranslate2.
- NLLB-200-distilled-600M : le [modèle Meta d’origine](https://huggingface.co/facebook/nllb-200-distilled-600M)
  est sous CC-BY-NC-4.0. La conversion int8 n’efface pas la restriction d’usage
  commercial. La v2 ne doit donc pas annoncer que tous ses modèles sont libres
  pour tous les usages.
- Données Tesseract et dictionnaires OCR : conserver les notices des dépôts
  exacts dont les révisions sont épinglées.

## Services en ligne et visuels

Edge TTS, gTTS et Google Traduction transmettent du texte à des services tiers.
La licence d’une bibliothèque cliente ne constitue pas une autorisation
d’utilisation ou de redistribution du service ; sa disponibilité peut évoluer.

Les icônes d’interface de `assets/icons/papirus/` viennent de **Papirus**, sous
GPL-3.0 ; voir [leur attribution](assets/icons/papirus/README.md).
L’icône principale est un visuel original généré ; sa provenance est documentée
dans [assets/icons/README.md](assets/icons/README.md).

## Contrôle de l’archive finale

Vérifier les notices, sources correspondantes et droits sur **l’archive finale**,
incluant `_internal`, les plugins Qt, les DLL Microsoft et `tools/`. Ne pas
embarquer les vidéos personnelles de `input/`, les autres vidéos d’essai, les
sorties, paramètres personnels ou caches de modèles. Seul `input/extrait.mkv`,
l’exemple livré avec la v1, est ajouté à la distribution. L’inventaire technique
aide à ce contrôle ; copier des notices
ne résout pas à lui seul les questions de droits encore ouvertes ci-dessus.
