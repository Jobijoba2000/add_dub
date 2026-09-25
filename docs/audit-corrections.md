# Corrections de l'audit et vérification manuelle

L'audit initial est conservé dans `AUDIT_COMPLET_2026-09-25.md` comme historique des défauts constatés, et non comme description du comportement corrigé.

## Changements

| Sujet de l'audit | Comportement corrigé |
|---|---|
| Collisions SRT et traductions | Dossier temporaire par vidéo, copies des SRT sélectionnés, priorité au sidecar courant. Cache de traduction indexé par identité de vidéo, sélection, contenu, langues, moteur et révisions. |
| Protection des sorties | Muxage provisoire, contrôle FFprobe, publication atomique ; remplacement explicite. Une sortie existante invalide n'est plus considérée comme terminée. |
| Réseau et confidentialité | TLS vérifié pour gTTS, délais de connexion/lecture, tâches TTS interrompues après blocage. CTranslate2 n'utilise plus Google en secours. `--offline` interdit les services distants et les téléchargements. |
| Encodages | Décodage commun UTF-8, UTF-8 avec BOM, UTF-16 avec BOM et CP1252 ; nettoyage d'une copie sans modifier le SRT utilisateur. |
| Synthèse | Processus isolés, aucune relance d'une tâche encore active, deux tentatives maximum pour les moteurs distants. Les erreurs Edge/gTTS ne deviennent plus du silence. |
| Traduction | Un paquet mal découpé est repris réplique par réplique. Une erreur ou une traduction incomplète fait échouer cette vidéo et n'est plus publiée comme succès. |
| Audio | Somme déterministe des cues superposés, saturation PCM à l'assemblage ; gains cohérents lecteur/export et limiteur commun. Copie de la piste audio originale sélectionnée, y compris ses canaux. |
| Mémoire | Ducking par blocs de 65 536 trames ; assemblage TTS dans un fichier mappé sur disque et export par blocs. L'espace disque temporaire reste proportionnel à la durée. |
| CLI et lots | Validation commune des nombres, rejet des options inconnues, résolution des chemins relatifs, SRT central reconnu. Une erreur par vidéo n'arrête plus les vidéos suivantes ; code final non nul. Les collisions de sorties sont refusées avant traitement. |
| OCR | Révisions fixes, téléchargement temporaire validé avant remplacement, refus du cache manifestement tronqué ; verrou interprocessus pour les réglages de langue. |
| Lecteur | Préparation des deux WAV avant publication, nettoyage des sorties du travail après échec/annulation, supervision des descendants. mpv n'est plus déclaré prêt avant l'événement de chargement. |
| GUI | Contrôle des sorties existantes en arrière-plan, arrêt possible pendant cette vérification ; sortie provisoire unique connue du superviseur. |
| Générateur HTML | Les valeurs affichées sont émises explicitement et désactiver la traduction produit `--no-translate`. |
| Distribution | Verrou de dépendances avec empreintes, révisions des modèles, CI Windows 2022/2025, tests médias et inventaire de distribution. |

La politique retenue est stricte : le moteur ne publie pas un résultat partiellement traduit ou partiellement vocalisé. Les interfaces indiquent l'échec et le journal donne la cause. La sélection manuelle d'un autre moteur permet de réessayer.

Le contrôle FFprobe vérifie la présence des flux et une durée positive ; il ne décode pas chaque trame d'un long film. Les sorties non validées sont conservées pour inspection et nécessitent `--overwrite` pour être remplacées.

## Tests automatisés

Validation réalisée le 25 septembre 2026 : **95 tests réussis** (59 avant corrections), `pip check` sans incompatibilité, installation du verrou dans une venv neuve, aperçu et lecteur Qt/mpv avec synthèse OneCore réelle réussis. La compilation complète avec `compil.bat` a réussi ; l'inventaire contient 60 paquets de l'environnement de compilation et 87 binaires natifs.

L'exécutable compilé a également produit un doublage OneCore hors ligne depuis un dossier temporaire, avec un PATH limité à Windows : les outils embarqués, les workers, les deux pistes audio, les sous-titres et `--skip-existing` ont été vérifiés. Cela ne remplace pas un test sur un autre poste Windows. Les essais interactifs de l'aperçu et du lecteur ont été faits depuis les sources.

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -v
.venv/Scripts/python.exe -m pip check
.venv/Scripts/python.exe tests/smoke_preview.py
.venv/Scripts/python.exe tests/smoke_player.py --tts --quick
.venv/Scripts/python.exe tests/smoke_distribution.py
```

La suite ajoute des tests de régression réseau, sous-titres, cache, annulation, publication et erreurs, ainsi que de vrais petits médias FFmpeg : codecs, conservation PCM multicanal, niveau du mix, pipeline, workers démarrés avec `spawn`. Le test JavaScript du générateur utilise Node.js et est ignoré si Node n'est pas installé.

Les essais Qt/mpv ouvrent brièvement des fenêtres et les ferment automatiquement. OneCore doit être installé pour les essais vocaux réels. Le test `--quick` couvre aussi le raccourci de vocalisation et la reprise automatique.

## Parcours manuel proposé

1. **GUI et aperçu** : lancer `start_add_dub.bat --gui`, ajouter un petit MKV, tester l'aperçu, pause, navigation, volumes et sous-titres, puis produire le doublage.
2. **Sources intactes** : vérifier qu'un SRT CP1252 avec accents est bien lu et que le fichier d'origine n'a pas changé.
3. **Homonymes** : placer deux vidéos `episode.mkv` dans deux dossiers, avec des textes distincts. Activer la conservation de l'arborescence et vérifier que les voix correspondent à chaque texte.
4. **Remplacement** : relancer une sortie existante sans remplacement, puis avec remplacement. Interrompre le second traitement ; la précédente sortie doit rester lisible.
5. **Traduction** : essayer Google puis CTranslate2. Sans modèle disponible, `--offline --tts-engine onecore --translation-engine ctranslate2` doit signaler l'absence du modèle sans envoyer le texte à Google.
6. **Lecteur** : lancer `--player`, sélectionner une piste, vocaliser, puis vérifier « Rejouer », « Continuer », le raccourci et l'annulation.
7. **Lot avec erreur** : mélanger une vidéo invalide et une vidéo valide ; vérifier que la seconde est traitée et que le lot signale un échec global.
8. **Audio original** : écouter la seconde piste d'une source multicanal ; elle doit conserver son codec et son nombre de canaux. Les AVI restent transcodés en H.264 côté vidéo, contrairement aux autres conteneurs copiés.

## Installation reproductible et entretien

`start_add_dub.bat` utilise désormais `requirements.lock.txt`. `requirements.txt` reste la liste courte des dépendances directes ; toute modification doit être reportée dans le verrou après résolution et tests. Les empreintes du verrou concernent CPython 3.12 / Windows x64.

Les révisions distantes se mettent à jour explicitement avec `scripts/lock_model_revisions.py`. Ajouter d'autres dépôts au registre est possible ; les nouveaux téléchargements n'utilisent jamais une branche flottante. Les anciens modèles locaux sont conservés ; les modèles épinglés utilisent un sous-dossier de révision, ce qui peut demander un nouveau téléchargement au premier usage.

Les SRT auparavant copiés dans le dossier central `srt/` ne sont pas supprimés automatiquement : ils peuvent aussi être des sources fournies manuellement. Nettoyer manuellement les anciennes copies ambiguës si nécessaire. Les traductions historiques ne sont pas réutilisées sans la nouvelle clé de cache.

Les deux alertes de dépendances restantes et les limites de validation sont détaillées dans [security-review.md](security-review.md). Une venv neuve sur ce poste ne remplace pas un essai sur une machine Windows vierge. La CI ne sera exécutée sur GitHub qu'après publication des changements.
