"""Téléchargement atomique de ressources OCR, avec contrôle du cache."""
import hashlib
import os
from pathlib import Path
import struct
import tempfile
import urllib.request
import xml.etree.ElementTree as ET


def validate_resource(path):
    raw = Path(path).read_bytes()
    if str(path).endswith('.xml'):
        ET.fromstring(raw)
    else:
        if len(raw) < 1024:
            raise ValueError('Modèle OCR incomplet.')
        count = struct.unpack_from('<I', raw)[0]
        if not 1 <= count <= 128 or len(raw) < 4 + count * 8:
            raise ValueError('En-tête du modèle OCR invalide.')
        offsets = struct.unpack_from(f'<{count}q', raw, 4)
        if any(value != -1 and not 4 + count * 8 <= value < len(raw) for value in offsets):
            raise ValueError('Contenu du modèle OCR tronqué.')
    return hashlib.sha256(raw).hexdigest()


def resource(url, destination, offline=False):
    destination = Path(destination)
    checksum = destination.with_suffix(destination.suffix + '.sha256')
    if destination.exists():
        try:
            digest = validate_resource(destination)
            if not checksum.exists() or checksum.read_text().strip() == digest:
                return str(destination)
        except (ValueError, OSError, ET.ParseError, struct.error):
            pass
    if offline:
        raise FileNotFoundError(f'Ressource OCR absente ou invalide en mode hors ligne : {destination}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(suffix=destination.suffix, dir=destination.parent)
    os.close(fd)
    try:
        with urllib.request.urlopen(url, timeout=30) as response, open(temporary, 'wb') as output:
            total = 0
            import time
            deadline = time.monotonic() + 180
            while chunk := response.read(65536):
                total += len(chunk)
                if total > 100 * 1024 * 1024 or time.monotonic() > deadline:
                    raise TimeoutError('Téléchargement OCR trop long ou trop volumineux.')
                output.write(chunk)
        digest = validate_resource(temporary)
        os.replace(temporary, destination)
        checksum.write_text(digest + '\n', encoding='ascii')
        return str(destination)
    finally:
        Path(temporary).unlink(missing_ok=True)
