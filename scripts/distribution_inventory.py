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
    for file in sorted((root / 'tools').rglob('*')):
        if file.is_file() and file.suffix.lower() in ('.exe', '.dll'):
            with file.open('rb') as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            binaries.append({'path': str(file.relative_to(root)), 'sha256': digest})
    inventory = {'python_environment': packages, 'native_tools': binaries,
                 'scope': 'Environnement de compilation Python et binaires tools livrés ; les licences restent à examiner.'}
    (root / 'THIRD_PARTY.json').write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Inventaire : {len(packages)} paquets, {len(binaries)} binaires natifs.')


if __name__ == '__main__':
    main()
