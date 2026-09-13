"""Déploie le moteur officiel LibVLC Windows, sans installation système."""
import hashlib
from pathlib import Path
import urllib.request
import zipfile

VERSION = '3.0.23'
SHA256 = '992d19dbd0b8a7cde9167d2f7780b1ef6f92acc8a71acfa736101a21f35181e1'
ROOT = Path(__file__).resolve().parents[1]


def main():
    target = ROOT / 'tools' / 'vlc'
    if (target / 'libvlc.dll').exists() and (target / 'VERSION').exists() and (target / 'VERSION').read_text() == VERSION:
        return
    archive = ROOT / '.cache' / f'vlc-{VERSION}-win64.zip'
    archive.parent.mkdir(exist_ok=True)
    if not archive.exists() or hashlib.sha256(archive.read_bytes()).hexdigest() != SHA256:
        print('Téléchargement du moteur VLC portable...')
        urllib.request.urlretrieve(f'https://download.videolan.org/pub/videolan/vlc/{VERSION}/win64/{archive.name}', archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != SHA256:
        raise RuntimeError('Archive VLC : empreinte SHA-256 incorrecte.')
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as package:
        for entry in package.infolist():
            parts = Path(entry.filename).parts[1:]
            if not parts or entry.is_dir():
                continue
            # Moteur et modules, sans application VLC, skins ni traductions UI.
            if parts[0] != 'plugins' and parts[-1] not in ('libvlc.dll', 'libvlccore.dll', 'COPYING', 'THANKS', 'AUTHORS'):
                continue
            output = target.joinpath(*parts).resolve()
            if not output.is_relative_to(target.resolve()):
                raise RuntimeError('Chemin inattendu dans l’archive VLC.')
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(package.read(entry))
    (target / 'VERSION').write_text(VERSION)
    print('Moteur VLC portable prêt.')


if __name__ == '__main__':
    main()
