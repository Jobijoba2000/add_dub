# add_dub/io/fs.py
import os


# On part du répertoire courant (le .bat fait déjà `cd /d "%~dp0"` à la racine)
ROOT = os.getcwd()

INPUT_DIR = os.path.join(ROOT, "input")
OUTPUT_DIR = os.path.join(ROOT, "output")
TMP_DIR = os.path.join(ROOT, "tmp")
# TMP_DIR = "N:/tmp/"


def ensure_base_dirs() -> None:
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(TMP_DIR, exist_ok=True)
    # Forcer les dossiers temporaires pour les libs qui lisent TEMP/TMP
    os.environ["TEMP"] = TMP_DIR
    os.environ["TMP"] = TMP_DIR


def join_input(path: str) -> str:
    return os.path.join(INPUT_DIR, path)


def join_output(path: str) -> str:
    return os.path.join(OUTPUT_DIR, path)
