# add_dub — Windows

Décompressez tout le dossier avant de lancer l’application. Les trois
exécutables partagent les outils et dépendances fournis avec la distribution.

| Exécutable | Mode par défaut |
|---|---|
| `add_dub.exe` | Interface graphique de doublage |
| `add_dub_console.exe` | Assistant console ; commandes CLI et batch |
| `add_dub_player.exe` | Lecteur avec vocalisation des sous-titres |

Le dossier `input/` contient `extrait.mkv` pour un premier essai. Dans le GUI,
cliquez sur **Ouvrir**, sélectionnez cette vidéo, puis choisissez les pistes et
la voix avant de lancer le traitement. Les exports vont dans `output/`.

Les préférences sont enregistrées dans `options.conf`, créé lors de
l’utilisation. `options.example.conf` fournit un exemple. Le lecteur conserve
ses propres réglages dans `player-data/`.

## Documentation

Ouvrez [docs/documentation.html](docs/documentation.html), puis cliquez sur le
bouton pour accéder au [manuel en ligne](https://jobijoba2000.github.io/add_dub/).

## Version et licences

`add_dub_console.exe --version` affiche la version. Le bouton **À propos et
licences** du GUI et le menu du lecteur affichent les notices disponibles.
Le projet est sous GNU GPLv3 : voir [LICENSE](LICENSE), les
[notices des composants tiers](THIRD_PARTY_NOTICES.md) et le dossier `licenses/`.
Les changements de cette version sont dans [CHANGELOG.md](CHANGELOG.md).
