"""Prépare les outils Windows locaux, sans dépendance Python tierce."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile

import prepare_mpv

ROOT = Path(__file__).resolve().parents[1]
# nom, destination, URL fixe, SHA-256, dossier dans l'archive, fichiers requis
PACKAGES = (
    ('FFmpeg', 'ffmpeg',
     'https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-8.1.2-full_build.7z',
     '0fff188997a499b5382e0f66e845d4556c48c54f0113ebed4853d556dbdd7059',
     'ffmpeg-8.1.2-full_build', ('bin/ffmpeg.exe', 'bin/ffprobe.exe')),
    ('MKVToolNix', 'MKVToolNix',
     'https://mkvtoolnix.download/windows/releases/94.0/mkvtoolnix-64-bit-94.0.7z',
     'c95fa8dd856c93cc5ec91900d650d0691f17bad5bf1f667b7d8b6752aaa23c8a',
     'mkvtoolnix', ('mkvmerge.exe', 'mkvextract.exe')),
    ('Subtitle Edit', 'subtitle_edit',
     'https://github.com/SubtitleEdit/subtitleedit/releases/download/4.0.13/SE4013.zip',
     'cf32b80696666f4fc2e44d07c1cfa48e8dcae90d8c381de3472598d66ab8af6a',
     '.', ('SubtitleEdit.exe',)),
    ('Tesseract', 'subtitle_edit/Tesseract550',
     'https://github.com/SubtitleEdit/support-files/releases/download/tesseract550/Tesseract550.zip',
     'ce7468cd4468b486e637632b76714d8c9c379780d659f7985639cb25428bb27e',
     '.', ('tesseract.exe', 'libtesseract-5.dll', 'tessdata')),
)


def ensure_subtitle_edit_settings(target, force=False):
    """Installe les réglages OCR connus sans écraser ceux de l'utilisateur."""
    if target.name != 'subtitle_edit':
        return
    source = Path(__file__).resolve().parent / 'assets' / 'subtitle_edit' / 'Settings.xml'
    destination = target / 'Settings.xml'
    if source.is_file() and (force or not destination.exists()):
        target.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        print('[Subtitle Edit] Configuration OCR par défaut installée.', flush=True)
    legacy = target / 'Tesseract302'
    if legacy.exists():
        shutil.rmtree(legacy)
        print('[Subtitle Edit] Ancien moteur Tesseract 3.02 retiré.', flush=True)


def digest(path):
    if not path.is_file():
        return None
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def download(url, target):
    print(f'  Téléchargement : {target.name}', flush=True)
    with urllib.request.urlopen(url, timeout=60) as response, target.open('wb') as output:
        total = int(response.headers.get('Content-Length', 0))
        received, last = 0, -1
        while chunk := response.read(1024 * 1024):
            output.write(chunk)
            received += len(chunk)
            percent = received * 100 // total if total else 0
            if total and percent // 10 != last:
                last = percent // 10
                print(f'\r  {min(percent, 100):3d} %', end='', flush=True)
        if total:
            print('\r  100 %')


def prepare_package(root, package):
    name, folder, url, expected, inner, required = package
    target = root / 'tools' / folder
    marker = target / '.add_dub_package'
    ensure_subtitle_edit_settings(target)
    if (marker.is_file() and marker.read_text().strip() == expected
            and all((target / item).exists() for item in required)):
        print(f'[{name}] Prêt.', flush=True)
        return
    cache = root / '.cache'
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / url.rsplit('/', 1)[1]
    with tempfile.TemporaryDirectory(prefix='tools-', dir=cache) as temporary:
        work = Path(temporary)
        if digest(archive) != expected:
            partial = work / archive.name
            download(url, partial)
            if digest(partial) != expected:
                raise RuntimeError(f'{name} : empreinte de téléchargement incorrecte.')
            os.replace(partial, archive)
        print(f'[{name}] Extraction...', flush=True)
        unpacked = work / 'unpacked'
        unpacked.mkdir()
        if archive.suffix == '.zip':
            with zipfile.ZipFile(archive) as source:
                source.extractall(unpacked)
        else:
            tar = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/tar.exe'
            subprocess.run([str(tar), '-xf', str(archive.resolve()), '-C', str(unpacked.resolve())],
                           check=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        payload = unpacked / inner
        if not all((payload / item).exists() for item in required):
            raise RuntimeError(f'{name} : contenu de l’archive inattendu.')
        fresh_target = not target.exists()
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            # Réparation : préserver réglages et modèles téléchargés par l'utilisateur.
            shutil.copytree(payload, target, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns('Settings.xml', '*.traineddata'))
        else:
            shutil.move(str(payload), str(target))
        marker.write_text(expected + '\n', encoding='ascii')
        ensure_subtitle_edit_settings(target, force=fresh_target)
        print(f'[{name}] Prêt.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT,
                        help='Racine de destination (pour préparation isolée).')
    args = parser.parse_args()
    root = args.root.resolve()
    for package in PACKAGES:
        prepare_package(root, package)
    prepare_mpv.main(root)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'[ERREUR] {error}', flush=True)
        raise SystemExit(1)
