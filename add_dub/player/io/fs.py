from pathlib import Path
import sys
import os

from add_dub.io.fs import ROOT as APP_ROOT
ROOT = Path(APP_ROOT)
TOOLS_DIR = ROOT / 'tools'
WORK_ROOT = ROOT / 'tmp' / 'player'
TMP_DIR = os.environ.get('ADD_DUB_GUI_WORK_TMP') or str(WORK_ROOT)
WAV_DIR = ROOT / 'player-data' / 'wav'
FFMPEG_DIR = TOOLS_DIR / 'ffmpeg' / 'bin'


def ensure_base_dirs():
    Path(TMP_DIR).mkdir(parents=True, exist_ok=True)
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    WAV_DIR.mkdir(parents=True, exist_ok=True)
    os.environ['TEMP'] = os.environ['TMP'] = str(TMP_DIR)
    os.environ['PATH'] = str(FFMPEG_DIR) + os.pathsep + os.environ.get('PATH', '')
