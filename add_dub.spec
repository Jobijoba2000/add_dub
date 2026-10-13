# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('models.lock.json', '.'), ('assets/icons/add_dub.ico', 'assets/icons'),
         ('assets/icons/add_dub_console.ico', 'assets/icons'),
         ('assets/icons/add_dub_player.ico', 'assets/icons'),
         ('assets/icons/papirus', 'assets/icons/papirus')]
binaries = []
hiddenimports = []

for pkg in ['ctranslate2', 'sentencepiece', 'langdetect', 'huggingface_hub', 'deep_translator']:
    try:
        tmp_ret = collect_all(pkg)
        datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
    except Exception:
        pass

hiddenimports += [
    'ctranslate2',
    'sentencepiece',
    'sentencepiece._sentencepiece',
]


a = Analysis(
    ['add_dub/__main__.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'PyQt6', 'PyQt6.QtCore', 'PyQt6.QtWidgets', 'PyQt6.QtGui', 'PyQt6_sip', 'qfluentwidgets', 'qframelesswindow', 'transformers', 'torch', 'torchvision', 'torchaudio', 'onnxruntime', 'scipy', 'matplotlib'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

launchers = []
for name, console in [('add_dub', False), ('add_dub_console', True), ('add_dub_player', False)]:
    launchers.append(EXE(
        pyz, a.scripts, [], exclude_binaries=True,
        name=name, icon=f'assets/icons/{name}.ico', version='scripts/windows_version.txt',
        debug=False, bootloader_ignore_signals=False,
        strip=False, upx=True, console=console,
        disable_windowed_traceback=False, argv_emulation=False,
        target_arch=None, codesign_identity=None, entitlements_file=None,
    ))
coll = COLLECT(
    *launchers,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='add_dub',
)
