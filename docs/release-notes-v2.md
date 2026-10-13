Cette v2 ajoute une interface graphique et un lecteur intégré, tout en conservant l’assistant console et le traitement batch de la v1.

## Nouveautés

- **Interface graphique** : ajout de vidéos ou de dossiers, traitement des sous-dossiers, réglages par vidéo, aperçu d’un extrait et file d’attente.
- **Lecteur mpv intégré** : lecture avec vocalisation des sous-titres, réglage des volumes et atténuation du son original. Les préférences sont enregistrées ; `Ctrl+Maj+D` lance la vocalisation avec les derniers réglages.
- **Paramètres généraux** : modification des préférences directement depuis l’interface.
- **Progression détaillée** : suivi des étapes, progression de l’OCR et estimation du temps restant.
- **Interface en cinq langues** : français, anglais, espagnol, allemand et italien.
- **Documentation actualisée** et notices des composants accessibles depuis le GUI et le lecteur.

## Corrections et améliorations

- Amélioration du mixage et du contrôle des volumes.
- Meilleure gestion de l’arrêt des processus et du nettoyage des fichiers temporaires.
- Correction des sous-titres qui dépassaient la fin des extraits.
- Correction de l’affichage des barres de progression du lecteur.

## Moteurs vocaux

- **Windows OneCore** : voix installées dans Windows, avec synthèse locale.
- **Edge TTS** : voix Microsoft en ligne.
- **gTTS** : voix Google en ligne.

## Trois lanceurs

Chaque exécutable possède sa propre icône et partage les dépendances de la distribution.

| Exécutable | Utilisation |
|---|---|
| `add_dub.exe` | Interface graphique, ouverte par défaut |
| `add_dub_console.exe` | Assistant interactif et commandes batch |
| `add_dub_player.exe` | Lecteur avec vocalisation des sous-titres |

## Installation et premier essai

1. Téléchargez `add_dub_v2.0.0_win64.zip`.
2. Décompressez entièrement l’archive.
3. Lancez `add_dub.exe`.
4. Cliquez sur **Ouvrir** et sélectionnez la vidéo d’exemple `input/extrait.mkv`.
5. Choisissez les pistes et la voix, ajoutez la vidéo à la file puis cliquez sur **Démarrer**.

## Compatibilité

- Windows 10/11 x64.
- L’OCR nécessite .NET Framework 4.8.
- Visual C++ x64 peut également être nécessaire.

📖 [Consulter la documentation en ligne](https://jobijoba2000.github.io/add_dub/)
