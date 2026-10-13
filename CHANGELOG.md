# Historique des versions

## 2.0.0

### Utilisation

- Nouvelle interface graphique pour préparer et traiter des lots de vidéos,
  avec réglages propres à chaque vidéo, aperçu mpv et file d’attente.
- Nouveau lecteur mpv : vocalisation des sous-titres, deux pistes WAV synchronisées,
  réglages enregistrés et lancement rapide avec Ctrl+Maj+D.
- Trois exécutables partageant les mêmes dépendances : `add_dub.exe` ouvre le
  GUI, `add_dub_console.exe` l’assistant/CLI et `add_dub_player.exe` le lecteur.
  Chacun possède une icône distincte.
- Éditeur général des préférences et commandes batch copiables.
- Interface traduite dans les cinq langues : français, anglais, espagnol,
  allemand et italien, y compris les explications, erreurs et messages d’état
  du GUI et du player.
- Version accessible avec `--version` et fenêtre À propos et licences.

### Voix et traitement

- Choix séparés de langue, région et voix.
- Meilleure gestion des pistes et de leurs métadonnées de langue.
- Mixage sans diminution automatique du gain par `amix` ; contrôle des volumes
  et de l’atténuation du son original.
- Progression par étape, total estimé, OCR en direct et durée restante estimée.
- Arrêt supervisé des processus, temporaires isolés et publication des exports
  après réussite. Une interruption conserve une sortie précédente.
- Correction des extraits : les sous-titres qui dépassent la fin sont coupés
  avant traduction, vocalisation et muxage.
- Barres du player à angles droits, sans padding intérieur.

### Distribution et documentation

- Préparation automatisée de Python, Visual C++ et des outils portables.
- Dépendances, révisions de modèles et téléchargements épinglés.
- Vérification TLS et délais pour les clients Google.
- README et manuel réorganisés ; notices des composants accessibles depuis
  l’application et livrées avec la distribution.
- Inventaire des EXE/DLL/PYD, incluant les composants de `_internal`.

Les conditions particulières des composants et modèles restent documentées
dans [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## 1.0.0 — release portable

- Assistant console et traitement batch.
- Extraction de sous-titres texte ou OCR, synthèse OneCore/Edge/gTTS,
  traduction, atténuation audio et export MKV.
- Outils portables embarqués pour Windows x64.
