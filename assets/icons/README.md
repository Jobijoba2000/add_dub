# Icône add_dub

Visuel original généré avec l'outil ImageGen intégré le 12 septembre 2026.
Source transparente : `assets/icons/add_dub.png`.
Icône Windows : `assets/icons/add_dub.ico`.

L'ICO contient 16, 20, 24, 32, 40, 48, 64, 96, 128 et 256 pixels.
Reconstruction : `.venv\Scripts\python.exe scripts\build_app_icon.py`.
La fenêtre utilise cet ICO ; PyInstaller l'embarque comme ressource de l'EXE
via `icon='assets/icons/add_dub.ico'`. Recompiler pour mettre à jour un EXE existant.

La v2 ajoute deux dessins SVG originaux sous la licence du projet :
`assets/icons/add_dub_console.svg` (bulle cyan et invite de terminal) et
`assets/icons/add_dub_player.svg` (bulle orange, lecture et audio). Le script construit
leurs ICO dans les mêmes dix tailles. Le GUI conserve l’icône principale ;
la console et le player utilisent chacun leur variante.

Les pictogrammes d’interface sont dans `assets/icons/papirus/`, avec leur
[attribution](papirus/README.md). Les ressources nécessaires sont embarquées
sous `_internal/assets/icons/` dans la distribution.

Tailles de référence : https://learn.microsoft.com/windows/apps/design/style/iconography/app-icon-construction

## Prompt ImageGen

Create a polished Windows desktop application icon for add_dub, a video dubbing application. Single original icon: a bold blue/cyan speech bubble integrated with a white play triangle, with a small warm orange audio accent. Elegant, coherent simple geometry, subtle premium depth and highlights, strong recognizable silhouette at 16px, no tiny details, no text or letters, no watermark. Front-facing centered square composition. Actual transparent background, icon occupies about 90 percent of canvas with only small safe margins. Crisp clean edges, bright attractive colors, no glow or cast shadow outside the icon. Output one 1024x1024 icon asset, not a mockup or sheet.
