# add_dub : Windows

Décompressez tout le dossier avant de lancer l’application. Les trois
exécutables partagent les outils et dépendances fournis avec la distribution.

| Exécutable | Mode par défaut |
|---|---|
| `add_dub.exe` | Interface graphique de doublage |
| `add_dub_console.exe` | Assistant console ; commandes CLI et batch |
| `add_dub_player.exe` | Lecteur avec vocalisation des sous-titres |

## Premier doublage

1. Ouvrez **`add_dub.exe`**.
2. Cliquez sur **Ouvrir** et choisissez vos vidéos ou un dossier sur votre ordinateur.
3. Choisissez les pistes audio et sous-titres, puis la voix.
4. Si vous le souhaitez, écoutez un extrait dans l’onglet **Essai**.
5. Cliquez sur **Ajouter à la liste d’attente**, puis sur **Démarrer**.

Les exports vont dans `output/` par défaut. Vous pouvez ouvrir les vidéos
directement à leur emplacement habituel. Pour tester avec l’exemple fourni,
choisissez `input/extrait.mkv`.

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
