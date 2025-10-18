# add_dub/io/fs.py

import os
from add_dub.config.effective import effective_values
from add_dub.config import cfg

# Racine du projet (le .bat fait déjà `cd /d "%~dp0"`)
ROOT = os.getcwd()

# Valeurs de secours si non définies dans defaults.py
_DEF_INPUT_DIR = getattr(cfg, "INPUT_DIR", "input")
_DEF_OUTPUT_DIR = getattr(cfg, "OUTPUT_DIR", "output")
_DEF_TMP_DIR = getattr(cfg, "TMP_DIR", "tmp")
_DEF_SRT_DIR = getattr(cfg, "SRT_DIR", "srt")  # SRT fixe à la racine (non modifiable)

# Dossiers **dynamiques** (initialisés sur defaults au chargement)
INPUT_DIR = os.path.join(ROOT, _DEF_INPUT_DIR)
OUTPUT_DIR = os.path.join(ROOT, _DEF_OUTPUT_DIR)
TMP_DIR = os.path.join(ROOT, _DEF_TMP_DIR)

# Dossier SRT **fixe** à la racine (non configurable)
SRT_DIR = os.path.join(ROOT, _DEF_SRT_DIR)

# Flags : l’utilisateur a-t-il surchargé via `set_base_dirs()` ?
_INPUT_OVERRIDDEN = False
_OUTPUT_OVERRIDDEN = False
_TMP_OVERRIDDEN = False


def _abspath_under_root(p: str) -> str:
    if not p:
        return ROOT
    return p if os.path.isabs(p) else os.path.join(ROOT, p)


def set_base_dirs(input_dir: str | None = None,
                  output_dir: str | None = None,
                  tmp_dir: str | None = None) -> None:
    """
    Change dynamiquement les répertoires. Si l’utilisateur passe par l’interactif,
    ses choix ne seront plus écrasés par `ensure_base_dirs()`.
    """
    global INPUT_DIR, OUTPUT_DIR, TMP_DIR
    global _INPUT_OVERRIDDEN, _OUTPUT_OVERRIDDEN, _TMP_OVERRIDDEN

    if input_dir is not None:
        INPUT_DIR = _abspath_under_root(str(input_dir))
        _INPUT_OVERRIDDEN = True
    if output_dir is not None:
        OUTPUT_DIR = _abspath_under_root(str(output_dir))
        _OUTPUT_OVERRIDDEN = True
    if tmp_dir is not None:
        TMP_DIR = _abspath_under_root(str(tmp_dir))
        _TMP_OVERRIDDEN = True


def ensure_base_dirs() -> None:
    """
    Initialise/crée les dossiers. On lit options.conf > defaults.py **une seule fois**
    (au premier appel), puis on respecte les overrides faits via `set_base_dirs()`.
    """
    global INPUT_DIR, OUTPUT_DIR, TMP_DIR

    fused = {}
    try:
        fused = effective_values() or {}
    except Exception:
        fused = {}

    # Appliquer les chemins de la conf **seulement** si non overridés par l’utilisateur
    if not _INPUT_OVERRIDDEN:
        conf_in = fused.get("input_dir", getattr(cfg, "INPUT_DIR", _DEF_INPUT_DIR))
        INPUT_DIR = _abspath_under_root(conf_in)
    if not _OUTPUT_OVERRIDDEN:
        conf_out = fused.get("output_dir", getattr(cfg, "OUTPUT_DIR", _DEF_OUTPUT_DIR))
        OUTPUT_DIR = _abspath_under_root(conf_out)
    if not _TMP_OVERRIDDEN:
        conf_tmp = fused.get("tmp_dir", getattr(cfg, "TMP_DIR", _DEF_TMP_DIR))
        TMP_DIR = _abspath_under_root(conf_tmp)

    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(TMP_DIR, exist_ok=True)
    os.makedirs(SRT_DIR, exist_ok=True)  # toujours présent et jamais effacé

    # Forcer les dossiers temporaires pour les libs qui lisent TEMP/TMP
    os.environ["TEMP"] = TMP_DIR
    os.environ["TMP"] = TMP_DIR


def join_input(path: str) -> str:
    return os.path.join(INPUT_DIR, path)


def join_output(path: str, output_dir=None) -> str:
    if output_dir is not None:
        base = _abspath_under_root(output_dir)
        return os.path.join(base, path)
    else:
        return os.path.join(OUTPUT_DIR, path)


def join_tmp(path: str) -> str:
    return os.path.join(TMP_DIR, path)


def join_srt(filename: str) -> str:
    return os.path.join(SRT_DIR, filename)
