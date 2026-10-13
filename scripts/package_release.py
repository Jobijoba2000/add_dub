"""Stage the portable distribution and optionally create its Windows ZIP."""
import argparse
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from add_dub.version import __version__

SAMPLE_VIDEO = Path('input/extrait.mkv')


def release_tag(value=None):
    if value is None:
        return f'v{__version__}'
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,99}', value) or '..' in value:
        raise ValueError('Tag invalide : utilisez des lettres, chiffres, points, tirets ou underscores, sans chemin.')
    return 'v' + value if value[0].isdigit() else value


def release_options(argv=None, *, description=__doc__, prog=None):
    parser = argparse.ArgumentParser(description=description, prog=prog)
    parser.add_argument('--zip', '--archive', dest='archive', action='store_true',
                        help='Créer le ZIP Windows après la préparation du dossier portable.')
    parser.add_argument('--tag', metavar='TAG',
                        help=f'Tag dans le nom du ZIP, par défaut v{__version__} (ex. v{__version__}-rc1).')
    args = parser.parse_args(argv)
    if args.tag is not None and not args.archive:
        parser.error('--tag nécessite --zip (ou --archive).')
    try:
        args.tag = release_tag(args.tag)
    except ValueError as exc:
        parser.error(str(exc))
    return args


def stage_sample(distribution):
    source = ROOT / 'scripts' / 'assets' / 'release' / 'extrait.mkv'
    if not source.is_file():
        raise FileNotFoundError(f'Missing release sample: {source}')
    destination = distribution / SAMPLE_VIDEO
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def stage_documentation(distribution):
    assets = ROOT / 'scripts' / 'assets' / 'release'
    source = assets / 'documentation.html'
    readme = assets / 'README-WINDOWS.md'
    if not source.is_file() or not readme.is_file():
        raise FileNotFoundError('Missing portable documentation assets')
    # Replace only this distribution's docs folder, never a linked directory.
    destination = distribution.resolve() / 'docs'
    if destination.resolve() != destination:
        raise ValueError(f'Unexpected documentation directory: {destination}')
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    shutil.copy2(source, destination / 'documentation.html')
    shutil.copy2(readme, distribution / 'README.md')
    # Notices point to bundled resources or the repository, rather than
    # documentation sources that are not shipped in the portable folder.
    notices = (ROOT / 'THIRD_PARTY_NOTICES.md').read_text(encoding='utf-8')
    for before, after in {
        '(assets/icons/papirus/README.md)': '(_internal/assets/icons/papirus/README.md)',
        '(assets/icons/README.md)': '(https://github.com/Jobijoba2000/add_dub/blob/main/assets/icons/README.md)',
    }.items():
        notices = notices.replace(before, after)
    (distribution / 'THIRD_PARTY_NOTICES.md').write_text(notices, encoding='utf-8')


def stage():
    distribution = ROOT / 'dist' / 'add_dub'
    for name in ('add_dub.exe', 'add_dub_console.exe', 'add_dub_player.exe'):
        if not (distribution / name).is_file():
            raise FileNotFoundError(f'Compile the launchers first: {name}')
    stage_sample(distribution)
    for name in ('ffmpeg', 'MKVToolNix', 'subtitle_edit', 'mpv'):
        shutil.copytree(ROOT / 'tools' / name, distribution / 'tools' / name,
                        dirs_exist_ok=True, ignore=shutil.ignore_patterns(
                            '*.log', '*.lock', 'preview.mkv', 'preview.srt', 'logs', '.cache'))
    # Never package Subtitle Edit's recent-file history or user-specific state.
    shutil.copy2(ROOT / 'scripts/assets/subtitle_edit/Settings.xml',
                 distribution / 'tools/subtitle_edit/Settings.xml')
    for name in ('options.example.conf', 'CHANGELOG.md', 'LICENSE',
                 'requirements.lock.txt', 'models.lock.json'):
        shutil.copy2(ROOT / name, distribution / name)
    stage_documentation(distribution)
    if (ROOT / 'licenses').is_dir():
        shutil.copytree(ROOT / 'licenses', distribution / 'licenses', dirs_exist_ok=True)
    subprocess.run([sys.executable, str(ROOT / 'scripts/distribution_inventory.py'), str(distribution)], check=True)
    return distribution


def archive(distribution, *, tag=None):
    tag = release_tag(tag)
    target = ROOT / 'dist' / f'add_dub_{tag}_win64.zip'
    excluded = {'input', 'output', 'srt', 'tmp', 'logs', 'player-data', '.cache'}
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as output:
        for path in sorted(distribution.rglob('*')):
            relative = path.relative_to(distribution)
            if not path.is_file() or relative == Path('options.conf'):
                continue
            # Keep the bundled example, while excluding personal input videos.
            if relative.parts[0] in excluded and relative != SAMPLE_VIDEO:
                continue
            output.write(path, str(Path('add_dub') / relative))
    print(f'Portable: {target.name} ({target.stat().st_size // 1024 // 1024} MiB)', flush=True)
    return target


if __name__ == '__main__':
    args = release_options()
    distribution = stage()
    if args.archive:
        archive(distribution, tag=args.tag)
