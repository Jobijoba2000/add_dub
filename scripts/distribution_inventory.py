"""Inventaire et notices des composants réellement livrés (sans analyse juridique)."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('distribution', type=Path)
    args = parser.parse_args()
    root = args.distribution.resolve()
    if not (root / 'add_dub.exe').is_file():
        parser.error('Le dossier ne contient pas add_dub.exe.')
    notices = root / 'licenses' / 'python'
    packages = []
    for dist in importlib.metadata.distributions():
        name = dist.metadata['Name']
        copied = []
        for file in dist.files or []:
            if any(part.lower().startswith(('license', 'copying', 'notice')) for part in file.parts):
                source = Path(dist.locate_file(file))
                if source.is_file():
                    target = notices / name / str(file).replace('..', '_')
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
                    copied.append(str(target.relative_to(root)))
        packages.append({'name': name, 'version': dist.version,
                         'license': dist.metadata.get('License-Expression') or dist.metadata.get('License'),
                         'notices': copied})
    binaries = []
    native_notices = []
    for file in sorted((root / 'tools').rglob('*')):
        if file.is_file() and file.name.lower().startswith(('license', 'copying', 'notice')):
            target = root / 'licenses' / 'native' / file.relative_to(root / 'tools')
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file, target)
            native_notices.append(str(target.relative_to(root)))
    # Qt, CTranslate2 and Python extensions also ship native
    # binaries under _internal. Include the launchers themselves, too.
    for file in sorted(root.rglob('*')):
        if file.is_file() and file.suffix.lower() in ('.exe', '.dll', '.pyd'):
            with file.open('rb') as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            binaries.append({'path': str(file.relative_to(root)), 'sha256': digest})
    inventory = {'python_environment': packages, 'native_tools': binaries,
                 'native_notices': native_notices,
                 'packages_without_notice_files': sorted(package['name'] for package in packages if not package['notices']),
                 'scope': 'Paquets de l’environnement de compilation (pas une liste des seuls imports livrés) et tous les EXE/DLL/PYD distribués. Les notices présentes sont copiées ; les absences et droits de redistribution restent à examiner.'}
    (root / 'THIRD_PARTY.json').write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Inventaire : {len(packages)} paquets, {len(binaries)} binaires natifs.')


if __name__ == '__main__':
    main()
