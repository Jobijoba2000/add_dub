# Corrections de l'audit et vérification manuelle

L'audit initial est conservé dans `AUDIT_COMPLET_2026-09-25.md` comme historique des défauts constatés, et non comme description du comportement corrigé.

## Rétablissement du fonctionnement antérieur

À la demande de l’utilisateur, les règles de sous-titres et l’encodage audio ont été repris depuis la révision `0f067bf`, antérieure à l’audit. Le changement de fonctionnement introduit par `97ca82c` était inapproprié.

- Toutes les extractions texte, conversions et OCR (PGS et VobSub) produisent de nouveau `srt/<nom vidéo>.srt`, conservé après le traitement et reproposé dans l’interface.
- La priorité du SRT central, la copie des fichiers externes, la sélection explicite d’une piste avec nouvelle extraction et les choix automatiques du batch retrouvent leurs règles antérieures.
- Les traductions retrouvent leurs noms visibles, leur réutilisation, les confirmations interactives et les choix de langue antérieurs. L’aperçu conserve ses traductions temporaires. Un échec de traduction retrouve le parcours antérieur : message puis possibilité de travailler avec le SRT source.
- Les deux pistes audio sont de nouveau encodées en stéréo avec le codec et le débit choisis, à partir du WAV extrait. La correction du niveau du mixage est conservée.
- Le décodage des accents, les corrections d’arrondi, les protections de fichiers et les délais réseau restent en place.

Les fichiers SRT temporaires déjà effacés par la version précédente ne sont pas récupérés automatiquement. Aucun SRT existant de l’utilisateur n’est supprimé ou renommé par cette restauration. Les fichiers de l’ancien cache `.translations` ne sont plus utilisés et restent sur disque.

## Changements

| Sujet de l'audit | Comportement corrigé |
|---|---|
| SRT et traductions | Règles historiques rétablies : SRT central persistant, priorité et noms antérieurs, réutilisation des traductions. Les autres fichiers de travail restent temporaires. |
| Protection des sorties | Muxage provisoire, contrôle FFprobe, publication atomique ; remplacement explicite. Une sortie existante invalide n'est plus considérée comme terminée. |
| Réseau et confidentialité | TLS vérifié pour gTTS, délais de connexion/lecture, tâches TTS interrompues après blocage. CTranslate2 n'utilise plus Google en secours. `--offline` interdit les services distants et les téléchargements. |
| Encodages | Décodage commun UTF-8, UTF-8 avec BOM, UTF-16 avec BOM et CP1252 ; nettoyage d'une copie sans modifier le SRT utilisateur. |
| Synthèse | Orchestration et assemblage de `0f067bf` rétablis à la demande de l’utilisateur : threads Edge/gTTS, processus OneCore, parallélisme et règles de reprise d’origine. Les protections réseau des moteurs restent en place. |
| Traduction | Un paquet mal découpé est repris réplique par réplique. Les erreurs sont signalées ; le parcours historique de reprise avec le SRT source est rétabli. |
| Audio | Placement des répliques selon le fonctionnement d’origine ; gains cohérents lecteur/export et limiteur commun. Encodage des deux pistes en stéréo avec le codec choisi, comme avant l’audit. |
| Mémoire | Ducking par blocs de 65 536 trames. Assemblage TTS en mémoire int16 avec chargement parallèle des segments, comme avant l’audit ; suppression du fichier mappé sur disque ajouté par l’audit. |
| CLI et lots | Validation commune des nombres, rejet des options inconnues, résolution des chemins relatifs, Priorités de sous-titres historiques rétablies. Une erreur par vidéo n'arrête plus les vidéos suivantes ; code final non nul. Les collisions de sorties sont refusées avant traitement. |
| OCR | Révisions fixes, téléchargement temporaire validé avant remplacement, refus du cache manifestement tronqué ; verrou interprocessus pour les réglages de langue. |
| Lecteur | Préparation des deux WAV avant publication, nettoyage des sorties du travail après échec/annulation, supervision des descendants. mpv n'est plus déclaré prêt avant l'événement de chargement. |
| GUI | Contrôle des sorties existantes en arrière-plan, arrêt possible pendant cette vérification ; sortie provisoire unique connue du superviseur. |
| Générateur HTML | Les valeurs affichées sont émises explicitement et désactiver la traduction produit `--no-translate`. |
| Distribution | Verrou de dépendances avec empreintes, révisions des modèles, CI Windows 2022/2025, tests médias et inventaire de distribution. |

Les erreurs de synthèse restent bloquantes ; la traduction retrouve son parcours historique de reprise avec le SRT source.

Le contrôle FFprobe vérifie la présence des flux et une durée positive ; il ne décode pas chaque trame d'un long film. Les sorties non validées sont conservées pour inspection et nécessitent `--overwrite` pour être remplacées.

## Tests automatisés

Validation initiale du commit `97ca82c` : **95 tests réussis** (59 avant corrections), `pip check` sans incompatibilité, installation du verrou dans une venv neuve, aperçu et lecteur Qt/mpv avec synthèse OneCore réelle réussis. La compilation complète avec `compil.bat` a réussi ; l'inventaire contient 60 paquets de l'environnement de compilation et 87 binaires natifs.

L'exécutable compilé a également produit un doublage OneCore hors ligne depuis un dossier temporaire, avec un PATH limité à Windows : les outils embarqués, les workers, les deux pistes audio, les sous-titres et `--skip-existing` ont été vérifiés. Cela ne remplace pas un test sur un autre poste Windows. Les essais interactifs de l'aperçu et du lecteur ont été faits depuis les sources.

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -v
.venv/Scripts/python.exe -m pip check
.venv/Scripts/python.exe tests/smoke_preview.py
.venv/Scripts/python.exe tests/smoke_player.py --tts --quick
.venv/Scripts/python.exe tests/smoke_distribution.py
```

La suite ajoute des tests de régression réseau, sous-titres, cache, annulation, publication et erreurs, ainsi que de vrais petits médias FFmpeg : codecs, conversion des sources multicanaux en stéréo, niveau du mix, pipeline, workers Edge exécutés dans des threads. Le test JavaScript du générateur utilise Node.js et est ignoré si Node n'est pas installé.

Les essais Qt/mpv ouvrent brièvement des fenêtres et les ferment automatiquement. OneCore doit être installé pour les essais vocaux réels. Le test `--quick` couvre aussi le raccourci de vocalisation et la reprise automatique.

Après rétablissement : **110 tests réussis**, dont les parcours persistants SRT texte/PGS/VobSub (outils OCR simulés), leur nouvelle détection dans l’interface, les traductions existantes et les confirmations interactives. Les tests médias vérifient les deux pistes stéréo et leur codec, ainsi que le niveau du mix. L’aperçu avec OneCore réel a été relancé avec succès. La distribution recompilée a réussi son essai OneCore hors ligne : SRT persistant, deux pistes stéréo et codec choisi. La recherche, copie, liste, extraction et résolution des sous-titres ont aussi été comparées automatiquement au code de `0f067bf` : leurs fonctions sont identiques.

## Parcours manuel proposé

1. **GUI et aperçu** : lancer `start_add_dub.bat --gui`, ajouter un petit MKV, tester l'aperçu, pause, navigation, volumes et sous-titres, puis produire le doublage.
2. **Sources intactes** : vérifier qu'un SRT CP1252 avec accents est bien lu et que le fichier d'origine n'a pas changé.
3. **Réutilisation SRT** : traiter une piste intégrée, puis rouvrir la vidéo et sélectionner le SRT conservé. Vérifier que l’extraction ou l’OCR n’est pas relancé.
4. **Remplacement** : relancer une sortie existante sans remplacement, puis avec remplacement. Interrompre le second traitement ; la précédente sortie doit rester lisible.
5. **Traduction** : essayer Google puis CTranslate2. Sans modèle disponible, `--offline --tts-engine onecore --translation-engine ctranslate2` doit signaler l'absence du modèle sans envoyer le texte à Google.
6. **Lecteur** : lancer `--player`, sélectionner une piste, vocaliser, puis vérifier « Rejouer », « Continuer », le raccourci et l'annulation.
7. **Lot avec erreur** : mélanger une vidéo invalide et une vidéo valide ; vérifier que la seconde est traitée et que le lot signale un échec global.
8. **Audio original** : écouter la seconde piste d'une source multicanal ; elle doit être en stéréo et utiliser le même codec choisi que la piste doublée. Les AVI restent transcodés en H.264 côté vidéo, contrairement aux autres conteneurs copiés.

## Installation reproductible et entretien

`start_add_dub.bat` utilise désormais `requirements.lock.txt`. `requirements.txt` reste la liste courte des dépendances directes ; toute modification doit être reportée dans le verrou après résolution et tests. Les empreintes du verrou concernent CPython 3.12 / Windows x64.

Les révisions distantes se mettent à jour explicitement avec `scripts/lock_model_revisions.py`. Ajouter d'autres dépôts au registre est possible ; les nouveaux téléchargements n'utilisent jamais une branche flottante. Les anciens modèles locaux sont conservés ; les modèles épinglés utilisent un sous-dossier de révision, ce qui peut demander un nouveau téléchargement au premier usage.

Les SRT et traductions historiques sont de nouveau réutilisés suivant les règles antérieures. Le dossier central est volontairement conservé avec sa convention de nommage d’origine.

Les deux alertes de dépendances restantes et les limites de validation sont détaillées dans [security-review.md](security-review.md). Une venv neuve sur ce poste ne remplace pas un essai sur une machine Windows vierge. La CI ne sera exécutée sur GitHub qu'après publication des changements.

## Affichage des durées en console

Les chronomètres TTS et ducking ont été rétablis. La progression termine sa ligne à 100 % avant l’affichage de la durée. La confirmation de remplacement est exécutée avant le démarrage du traitement chronométré ; une sortie ignorée ou un remplacement refusé ne lance pas ce chronomètre. Validation : 114 tests réussis, dont quatre tests dédiés aux durées et à l’affichage console.

## Retour au traitement TTS d’origine

Le module `add_dub/core/tts_generate.py` a été restauré intégralement depuis `0f067bf`, avec vérification de l’absence de différence. Le pool unique de huit processus, l’attente explicite `join()` à 90 %, l’accumulation int32 sur disque et l’export par blocs introduits par l’audit sont retirés. Les threads Edge/gTTS, les processus OneCore (jusqu’à 20), le chargement parallèle (jusqu’à 32 threads), le tableau int16 en mémoire et l’export WAV d’origine sont rétablis, ainsi que les règles historiques de placement et de reprise. Les chronomètres et leur affichage corrigé sont conservés.

Validation : 114 tests réussis. Les tests de la stratégie retirée sont remplacés par des vérifications des types d’exécuteurs, du parallélisme, de l’absence de fichier mappé sur disque, du placement des échantillons, du nettoyage et des durées affichées. Aucun temps précis n’est garanti pour le média personnel de l’utilisateur, qui n’a pas été utilisé pour cette vérification.
