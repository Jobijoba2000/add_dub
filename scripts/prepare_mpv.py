"""Prépare le libmpv Windows x64 partagé par --gui et --player."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
VERSION = '20260903-git-69e63f425a'
ARCHIVE = f'mpv-dev-x86_64-{VERSION}.7z'
URL = f'https://github.com/shinchiro/mpv-winbuild-cmake/releases/download/20260903/{ARCHIVE}'
ARCHIVE_SHA256 = 'fac135c68a35b7639e39d72c0c365104edbaebdea39a0dfdd8c36e8c8e80faef'
DLL_SHA256 = '673e6397920ab64a9c5b3a618f7f16d38854efe72b58665f1f84e4e873b763a4'


def digest(path):
    if not path.is_file():
        return None
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main(root=ROOT):
    root = Path(root)
    target = root / 'tools' / 'mpv' / 'libmpv-2.dll'
    if digest(target) == DLL_SHA256:
        return
    cache = root / '.cache'
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / ARCHIVE
    # Windows fournit tar.exe : aucun extracteur supplémentaire à installer.
    tar = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' / 'tar.exe'
    if not tar.is_file():
        raise RuntimeError('tar.exe Windows est nécessaire à la préparation des sources mpv.')
    with tempfile.TemporaryDirectory(prefix='mpv-', dir=cache) as work:
        work = Path(work)
        if digest(archive) != ARCHIVE_SHA256:
            print('Téléchargement du moteur mpv portable…', flush=True)
            downloaded = work / ARCHIVE
            with urllib.request.urlopen(URL, timeout=60) as response, downloaded.open('wb') as output:
                shutil.copyfileobj(response, output)
            if digest(downloaded) != ARCHIVE_SHA256:
                raise RuntimeError('Archive mpv : empreinte SHA-256 incorrecte.')
            os.replace(downloaded, archive)
        # Extraction du seul membre attendu, jamais de chemins libres de l'archive.
        subprocess.run([str(tar), '-xf', str(archive.resolve()), '-C', str(work.resolve()), 'libmpv-2.dll'],
                       check=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        library = work / 'libmpv-2.dll'
        if digest(library) != DLL_SHA256:
            raise RuntimeError('Bibliothèque mpv : empreinte SHA-256 incorrecte.')
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(library, target)
    print('Moteur mpv portable prêt.', flush=True)


if __name__ == '__main__':
    main()
