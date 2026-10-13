"""Package the main artwork and two original SVG launcher icons into ICOs.

Usage: .venv/Scripts/python.exe scripts/build_app_icon.py
Uses the project's Qt dependency; no additional image library is required.
"""
import struct
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parents[1]
ICON_DIR = ROOT / 'assets' / 'icons'
SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)


def build(name='add_dub'):
    if name == 'add_dub':
        source = QImage(str(ICON_DIR / 'add_dub.png'))
    else:
        renderer = QSvgRenderer(str(ICON_DIR / (name + '.svg')))
        if not renderer.isValid():
            raise ValueError(f'Invalid launcher SVG: {name}')
        source = QImage(256, 256, QImage.Format.Format_ARGB32)
        source.fill(Qt.GlobalColor.transparent)
        painter = QPainter(source)
        renderer.render(painter)
        painter.end()
    if source.isNull() or source.width() != source.height():
        raise ValueError('Expected a square assets/icons/add_dub.png image')
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
    target = ICON_DIR / (name + '.ico')
    target.write_bytes(struct.pack('<HHH', 0, 1, len(SIZES)) + b''.join(entries) + b''.join(images))
    print(f'{target}: {", ".join(map(str, SIZES))} px')


if __name__ == '__main__':
    for name in ('add_dub', 'add_dub_console', 'add_dub_player'):
        build(name)
