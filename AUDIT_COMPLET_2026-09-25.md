# Audit technique — add_dub

Date : 25 septembre 2026. Révision examinée : `0f067bf`.

## Conclusion

Le projet possède une séparation utile entre interfaces, pipeline et adaptateurs, ainsi qu'une bonne base de tests pour le cycle de vie des processus. Les principaux risques se trouvent dans l'intégrité des sous-titres, la gestion des échecs du moteur et les différences de comportement entre console, GUI et lecteur. Les tests actuels ne suffisent pas à valider la justesse du doublage produit.

Priorité proposée : corriger les collisions et la publication des sorties, sécuriser les appels réseau, puis fiabiliser traduction et synthèse avant d'étendre les fonctionnalités.

## Périmètre et vérifications

- Inventaire : 68 modules Python applicatifs, environ 11 891 lignes.
- Revue des chemins critiques CLI, GUI, lecteur, configuration, fichiers, sous-titres, traduction, synthèse, ducking, FFmpeg, installation et compilation ; inspection du générateur HTML et de la documentation. Profondeur variable selon les composants, et non preuve formelle de chaque ligne.
- ` .venv\Scripts\python.exe -m unittest discover -s tests -v` : **59 tests réussis en 13,681 secondes**, sans échec annoncé.
- `.venv\Scripts\python.exe -m pip check` : **No broken requirements found**. Cela vérifie la cohérence des dépendances, pas leurs vulnérabilités.
- Reproductions isolées sur des SRT synthétiques ; appels de traduction remplacés par des mocks, sans transmission de contenu à un service.
- Lecture de l'aide du FFmpeg embarqué : `amix` active `normalize` par défaut.
- Inspection du code effectivement installé de gTTS et deep-translator pour les paramètres TLS et les délais réseau.
- Aucun changement au code applicatif. Seul ce rapport est ajouté. Les tests peuvent créer des journaux et caches ignorés par Git.

Non vérifié : compilation complète et archive distribuée, installation sur Windows vierge, vrai doublage long avec chacun des moteurs, OCR réel, qualité linguistique, accessibilité avec lecteur d'écran, consommation mémoire mesurée, scan CVE exhaustif des dépendances Python et binaires natifs, historique Git à la recherche de secrets. Aucune conclusion d'absence de vulnérabilités ne découle de cet audit.

P1 = à traiter en priorité (intégrité des résultats, confidentialité ou sécurité). P2 = défaut fonctionnel ou de robustesse à programmer. Les observations statiques sont distinguées des reproductions.

## Constats prioritaires

### 1. P1 — Un film peut recevoir les sous-titres d'un autre

**Fichiers :** `add_dub/core/subtitles.py:39`, `:53`, `:340` ; `add_dub/cli/batch.py:149` ; `add_dub/core/pipeline.py:152`.

Le dossier partagé `srt/` utilise uniquement le nom du fichier, sans identité de dossier ou de piste. En batch automatique, le choix `('srt', None)` donne priorité à cette copie avant le sidecar réel. Deux vidéos `A/episode.mp4` et `B/episode.mp4` utilisent donc le même SRT. Même avec une sélection explicite qui renouvelle la copie, les traductions partagent une clé fondée sur le basename et la langue, sans validation du contenu source. `--preserve-tree` ne résout pas le problème des SRT.

**Reproduit :** les sidecars contiennent respectivement `first movie` et `second movie` ; la résolution de B retourne `first movie` après A.

**Correction :** isoler chaque travail ; identifier le cache par chemin normalisé, piste, contenu source et paramètres de traduction. Faire primer la sélection explicite et le sidecar courant. Tester deux films homonymes et un SRT modifié entre deux exécutions.

### 2. P1 — Le batch et la console écrivent directement sur la sortie finale

**Fichiers :** `add_dub/core/pipeline.py:67`, `:350` ; `add_dub/adapters/ffmpeg.py:167` ; `add_dub/gui/run.py:37`.

Hors environnement GUI, le muxage utilise directement le chemin final et FFmpeg reçoit `-y`. Un fichier existant peut être remplacé sans `--overwrite` si `--skip-existing` n'est pas fourni. Une interruption ou une erreur de muxage peut laisser une sortie tronquée ; un lancement ultérieur avec `--skip-existing` considère sa simple existence comme suffisante. La protection par sortie provisoire existe déjà pour la GUI, mais pas pour tous les modes.

**Preuve :** parcours statique des arguments FFmpeg et du choix de `mux_output` ; aucun fichier utilisateur n'a été écrasé pour cet audit.

**Correction :** publication atomique commune à tous les modes après validation FFprobe ; politique explicite pour les sorties existantes et suppression des seuls fichiers provisoires appartenant au travail.

### 3. P1 — gTTS installé désactive la validation TLS

**Fichiers :** `requirements.txt:9` ; `add_dub/core/tts_gtts.py:204` ; `.venv/Lib/site-packages/gtts/tts.py:270`.

Le gTTS 2.5.4 utilisé par le projet appelle `Session.send(..., verify=False, ...)`. Le texte envoyé à la synthèse et la réponse audio ne bénéficient donc pas de l'authentification du certificat serveur. Un intermédiaire réseau actif capable d'intercepter la connexion pourrait lire ou modifier ces échanges.

**Preuve :** lecture du code de la dépendance installée ; aucun test d'interception réalisé. Il s'agit d'un comportement de la dépendance, pas d'un `verify=False` écrit dans add_dub.

**Correction :** utiliser une intégration qui impose la validation TLS et ajouter une vérification de ce paramètre. Ne pas supposer qu'une mise à jour corrige ce comportement sans inspecter et tester la version retenue.

### 4. P1 — CTranslate2 peut envoyer les sous-titres à Google en secours

**Fichier :** `add_dub/core/translation.py:580`.

Après échec des modèles locaux, le moteur `ctranslate2` appelle Google automatiquement. Le journal prévient, mais aucune politique distincte ne permet de garantir un traitement local. Un utilisateur choisissant ce moteur pour garder son texte local peut donc provoquer un transfert réseau inattendu. Le téléchargement des modèles est également automatique lorsque nécessaire.

**Reproduit avec mocks :** Opus et NLLB indisponibles, `engine='ctranslate2'` → `_translate_with_google` appelé.

**Correction :** séparer le choix du moteur et l'autorisation de secours réseau ; fournir un mode local strict et rendre les transferts compréhensibles dans l'interface.

## Fiabilité du traitement

### 5. P2 — Le nettoyage détruit les accents des SRT Windows-1252

**Fichier :** `add_dub/core/subtitles.py:64`.

`strip_subtitle_tags_inplace` lit en UTF-8 avec remplacement des erreurs, puis réécrit le fichier. Le fallback CP1252 du parseur intervient trop tard : les octets sont déjà perdus dans la copie de travail. Un SRT directement utilisé dans `srt/` est lui-même modifié.

**Reproduit :** `été français` devient `�t� fran�ais` après nettoyage, alors que le parseur seul le lisait correctement.

**Correction :** centraliser le décodage avant nettoyage, avec UTF-8/BOM et fallback contrôlé ; préserver la source. Ajouter des cas UTF-8, CP1252 et BOM.

### 6. P2 — Un délai de cinq secondes déclenche des synthèses en double

**Fichier :** `add_dub/core/tts_generate.py:145-220`.

Si aucune future ne termine en cinq secondes, tous les travaux restants sont rejoués synchroniquement. Le résultat de `cancel()` n'est pas contrôlé ; une tâche déjà en cours n'est pas annulée. Les versions initiales peuvent continuer pendant la duplication, produire des WAV non collectés et augmenter la charge réseau. `shutdown(wait=False)` ne les arrête pas. La supervision batch ferme les descendants en fin de traitement, mais ne prévient pas cette duplication.

**Preuve :** branche statique ; vérification locale qu'une `Future` déjà active retourne `False` à `cancel()`. Pas de simulation de panne réseau réelle.

**Correction :** distinguer attente, timeout et échec ; ne relancer qu'une tâche terminée ou effectivement interrompue, avec nombre de tentatives borné.

### 7. P2 — Des requêtes réseau peuvent bloquer sans délai maximal

**Fichiers :** `add_dub/core/tts_gtts.py:204` ; `.venv/Lib/site-packages/gtts/tts.py:123` ; `.venv/Lib/site-packages/deep_translator/google.py:67`.

gTTS est construit sans `timeout`, dont la valeur installée par défaut est `None`. GoogleTranslator appelle `requests.get` sans timeout. Un serveur qui ne termine pas sa réponse peut immobiliser le travail ; la relance synchrone du point 6 aggrave le cas TTS. Le superviseur batch attend la fin du traitement avant d'appliquer sa période de fermeture.

**Correction :** délais de connexion/lecture explicites, budget total, retries bornés et propagation de l'annulation.

### 8. P2 — Une traduction Google mal découpée reste déclarée exploitable

**Fichier :** `add_dub/core/translation.py:488-495`.

Si Google ne conserve pas les séparateurs `###`, le code complète avec les derniers textes originaux ou tronque l'excédent. Le nombre final d'éléments peut sembler correct malgré une mauvaise association aux timestamps.

**Reproduit avec mock :** deux répliques `Hello.` / `Goodbye.`, réponse fusionnée `Bonjour. Au revoir.` → résultat `['Bonjour. Au revoir.', 'Goodbye.']`.

**Correction :** exiger une correspondance exacte ; en cas d'écart, traduire individuellement les lignes du paquet ou signaler l'échec.

### 9. P2 — Des erreurs de traduction produisent un succès apparent

**Fichiers :** `add_dub/core/translation.py:304`, `:416` ; `add_dub/core/pipeline.py:281`.

Opus/NLLB remplacent un paquet en erreur par le texte source. Le pipeline peut aussi continuer après une exception de traduction. Le traitement termine alors avec des sous-titres entièrement ou partiellement non traduits, potentiellement lus par une voix cible et étiquetés dans une autre langue.

**Preuve :** lecture des branches d'exception et de la construction du résultat.

**Correction :** retourner un statut structuré avec les répliques en échec ; différencier succès, résultat dégradé et échec dans CLI/GUI ; rendre le repli explicite.

### 10. P2 — Le mix exporté ne respecte pas les mêmes gains que le lecteur

**Fichiers :** `add_dub/adapters/ffmpeg.py:159-162` ; `add_dub/adapters/mpv.py:224`.

L'export laisse `amix` normaliser ses deux entrées ; le lecteur utilise explicitement `normalize=0`. Avec deux entrées présentes et des poids égaux, l'export divise leur somme par deux, soit environ -6 dB par rapport à la somme non normalisée. Cela vaut aussi lorsque l'une contient du silence ou est mise à zéro par le filtre `volume`. Les mêmes réglages donnent donc des niveaux différents selon le mode.

**Preuve :** aide du FFmpeg embarqué : `normalize ... (default true)`, et comparaison des deux filtres. Pas de mesure acoustique utilisateur.

**Correction :** définir une politique de gain commune, avec protection contre l'écrêtage, puis comparer les niveaux sur des signaux synthétiques.

### 11. P2 — Les voix de sous-titres qui se chevauchent s'écrasent

**Fichier :** `add_dub/core/tts_generate.py:299`.

Des threads écrivent leurs segments dans le même tableau via affectation. Deux cues qui se chevauchent remplacent leurs échantillons mutuellement ; le résultat dépend de l'ordre d'exécution, au lieu d'une règle audio déterministe.

**Preuve :** analyse des plages partagées et de l'exécution parallèle ; aucune mesure de fréquence du problème.

**Correction :** choisir une politique explicite de chevauchement (mixage avec limiteur, priorité ou ajustement temporel) et assembler de façon déterministe. Ajouter un cas avec deux cues superposés.

### 12. P2 — La validation CLI est moins stricte que celle des interfaces

**Fichiers :** `add_dub/cli/args.py:66-79` ; `add_dub/__main__.py:37` ; `add_dub/gui/model.py:47`.

La CLI accepte des valeurs non finies, des durées/vitesses invalides et des bornes inversées. Les arguments inconnus retournés par `parse_known_args` sont ignorés dans l'entrée principale, donc une faute de frappe peut changer silencieusement le comportement.

**Reproduit :** `--min-rate-tts inf --max-rate-tts -1 --bg-mix nan --overwite` est accepté par le parseur ; seule la dernière option figure dans la liste inconnue que l'entrée ignore.

**Correction :** validation partagée des options pour tous les modes, rejet des valeurs non finies et des arguments inconnus, erreurs lisibles avant tout traitement.

### 13. P2 — Une exception sur une vidéo arrête tout le lot CLI

**Fichier :** `add_dub/cli/batch.py:277`.

La boucle gère un retour vide du pipeline mais pas ses exceptions. Une erreur FFmpeg, TTS ou disque sur une vidéo interrompt les fichiers suivants. Le booléen `any_error` ne couvre donc pas ces cas.

**Preuve :** parcours statique jusqu'au superviseur, qui n'effectue pas de reprise fichier par fichier.

**Correction :** capturer les erreurs au niveau de chaque vidéo, préserver le diagnostic, nettoyer son travail et poursuivre selon une politique de lot explicite ; retourner un code global non nul en cas d'échecs.

### 14. P2 — La piste présentée comme originale est réencodée en stéréo

**Fichier :** `add_dub/adapters/ffmpeg.py:96`, `:188-196` ; `README.md`, structure du flux.

L'extraction impose deux canaux ; le muxage prend ce WAV et le réencode dans le codec choisi. Une piste 5.1/7.1 ou lossless n'est donc pas préservée à l'identique. Les autres pistes audio ne sont pas mappées. Par ailleurs les AVI sont transcodés en H.264, malgré la présentation générale d'une vidéo sans perte.

**Preuve :** mapping et options FFmpeg. Le média source sur disque n'est pas modifié ; le constat concerne le résultat exporté.

**Correction :** copier directement la piste originale depuis la source si la préservation est attendue ; sinon documenter précisément le downmix, le réencodage et l'exception AVI.

## Autres limites concrètes

- **Téléchargements OCR non atomiques** — `add_dub/adapters/subtitle_edit.py:73-85`, `:99-108` : écriture directement dans la cible, puis test de seule existence. Un téléchargement interrompu peut laisser un fichier incomplet qui ne sera plus téléchargé. Utiliser un fichier temporaire, valider son contenu puis le publier ; pinner les ressources lorsqu'une reproductibilité stricte est souhaitée.
- **WAV orphelins après échec du lecteur** — `add_dub/player/core/generation.py:62` publie la voix avant extraction/ducking. En cas d'échec ultérieur, le dialogue nettoie seulement `self.work`, pas les sorties dans `player-data/wav/`. Conserver les deux WAV dans le travail jusqu'au succès ou nettoyer leurs chemins attribués au travail.
- **Chemins relatifs batch** — `add_dub/cli/batch.py:69`, `:95` : la conversion immédiate en absolu empêche ensuite le fallback annoncé vers `INPUT_DIR`, car joindre un chemin absolu ignore le premier argument. Résoudre séparément le chemin utilisateur et le candidat relatif à l'entrée.
- **SRT central ignoré en sélection automatique** — `add_dub/cli/batch.py:147-153` : sans sidecar, `auto` force `('mkv', 0)` même si `srt/<nom>.srt` existe ; cela contredit notamment le cas MP4 accompagné uniquement d'un SRT central. Tester explicitement ce parcours.
- **Diagnostics FFmpeg perdus** — `add_dub/adapters/ffmpeg.py:29` : `stderr=DEVNULL` supprime la cause technique des erreurs. Conserver une fin de journal bornée pour le message d'échec.
- **Codecs incohérents** — `core/codecs.py` construit des arguments normalisés, mais `adapters/ffmpeg.py:194` utilise directement `opts.audio_codec`. Les alias et paramètres ne passent pas par une source unique. Tester tous les codecs proposés sur un clip court avant de garantir leur prise en charge.
- **Générateur HTML dépendant de la configuration locale** — `generator/generator.html:566` et suivants : désactiver Traduction n'émet pas `--no-translate`, et plusieurs valeurs affichées ne sont pas émises si elles valent le défaut de la page. Avec des valeurs différentes dans `options.conf`, la commande n'applique pas nécessairement les réglages visibles. Émettre les choix explicitement.

## Performance, architecture et maintenance

Le ducking charge le WAV complet, un tableau float32 stéréo, une enveloppe float32, puis plusieurs tableaux de conversion. Pour deux heures à 48 kHz stéréo, les tailles de base sont environ 1,38 Go de PCM16, 2,76 Go de float32 stéréo et 1,38 Go d'enveloppe, avant les copies d'export. Ce sont des estimations par dimensions, pas une mesure du pic réel. Un traitement par blocs réduirait fortement le risque mémoire sur les longs films.

Les dossiers et certaines préférences sont des variables globales modifiées à l'exécution. L'isolation par processus limite le problème dans la GUI ; elle ne remplace pas un contexte de travail explicite, notamment pour `SRT_DIR`. Les conversions de langues, de codecs et la validation des options ont plusieurs implémentations dont les comportements divergent.

Les dépendances directes sont généralement épinglées, mais `huggingface_hub>=0.20.0`, les dépendances transitives et les téléchargements de modèles sans révision fixe empêchent de reproduire exactement un environnement neuf. Aucun workflow CI suivi dans `.github` n'a été trouvé. Prévoir un lock reproductible, une matrice Windows et un inventaire des composants distribués. La conformité des licences des binaires doit être vérifiée sur l'archive réellement distribuée ; le présent audit ne constitue pas une revue juridique.

## Points solides

- Les commandes applicatives examinées utilisent généralement des listes d'arguments sans shell.
- Les principaux outils téléchargés et Python ont des empreintes SHA-256 fixes ; l'installateur Visual C++ est contrôlé par signature Microsoft.
- La GUI possède déjà un mécanisme de publication atomique et des garde-fous de nettoyage, couverts par tests.
- La supervision batch utilise un Job Object Windows et teste plusieurs cas de processus descendants et de fin anormale.
- Les interfaces valident les réglages numériques, le lecteur enregistre ses paramètres par remplacement atomique et mpv désactive le chargement de scripts/configuration utilisateur.

## Plan de correction et critères de validation

1. **Intégrité et confidentialité :** identité robuste des SRT/traductions, publication atomique commune, TLS vérifié, mode local strict. Valider deux homonymes, une source modifiée et une interruption pendant remplacement d'une sortie existante.
2. **Moteur :** décodage SRT commun, retries TTS bornés, timeouts, traduction à correspondance stricte et statut dégradé. Ajouter des tests ciblés sur les défauts reproduits.
3. **Cohérence audio :** gains identiques lecteur/export, chevauchements déterministes et politique de conservation de l'original. Mesurer durée, niveau et nombre de canaux sur un petit média synthétique.
4. **Exploitation :** erreurs par vidéo, diagnostics FFmpeg, nettoyage des WAV après échec et téléchargement OCR atomique.
5. **Validation de distribution :** tests CI Windows, compilation propre, lancement console/GUI/lecteur depuis l'archive et essai sur machine sans outils préinstallés ; analyse de dépendances/CVE et inventaire des licences sur cette archive.

L'objectif de la prochaine suite de tests doit être la validité du média produit et la conservation des données, en complément des 59 tests actuels principalement consacrés aux interfaces et aux processus.
