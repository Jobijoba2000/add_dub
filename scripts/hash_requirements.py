"""Ajoute les SHA-256 des archives téléchargées aux versions verrouillées."""
import hashlib
from pathlib import Path
from packaging.utils import canonicalize_name, parse_wheel_filename, parse_sdist_filename

ROOT = Path(__file__).resolve().parents[1]


def main():
    artifacts = {}
    for path in (ROOT / '.cache' / 'locked-wheels').iterdir():
        if path.suffix == '.whl':
            name, version, *_ = parse_wheel_filename(path.name)
        else:
            name, version = parse_sdist_filename(path.name)
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        artifacts.setdefault((canonicalize_name(name), str(version)), []).append(digest)
    lock = ROOT / 'requirements.lock.txt'
    lines = ['# Windows x64 / CPython 3.12. Archives vérifiées pour cet environnement.']
    for line in lock.read_text(encoding='utf-8').splitlines():
        if not line or line.startswith('#'):
            continue
        requirement = line.split(' --hash=')[0]
        name, version = requirement.split('==')
        hashes = artifacts[(canonicalize_name(name), version)]
        lines.append(requirement + ''.join(' --hash=sha256:' + digest for digest in sorted(hashes)))
    lock.write_text('\n'.join(lines) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
