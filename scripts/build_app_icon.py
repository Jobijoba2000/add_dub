"""Package the approved PNG artwork into a Windows multi-resolution ICO.

Usage: .venv/Scripts/python.exe scripts/build_app_icon.py
Uses the project's Qt dependency; no additional image library is required.
"""
import struct
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QImage

ROOT = Path(__file__).resolve().parents[1]
SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)


def build():
    source = QImage(str(ROOT / 'docs' / 'add_dub.png'))
    if source.isNull() or source.width() != source.height():
        raise ValueError('Expected a square docs/add_dub.png image')
    entries, images = [], []
    offset = 6 + 16 * len(SIZES)
    for size in SIZES:
        scaled = source.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if not scaled.save(buffer, 'PNG'):
            raise RuntimeError(f'Cannot encode {size}px icon')
        data = bytes(buffer.data())
        entries.append(struct.pack('<BBBBHHII', size % 256, size % 256, 0, 0,
                                   1, 32, len(data), offset))
        images.append(data)
        offset += len(data)
    target = ROOT / 'docs' / 'add_dub.ico'
    target.write_bytes(struct.pack('<HHH', 0, 1, len(SIZES)) + b''.join(entries) + b''.join(images))
    print(f'{target}: {", ".join(map(str, SIZES))} px')


if __name__ == '__main__':
    build()
