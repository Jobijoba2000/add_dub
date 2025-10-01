# add_dub/config/opts_loader.py
from __future__ import annotations
import os, re, shutil
from dataclasses import dataclass
from typing import Any, Dict

@dataclass
class OptEntry:
    value: Any
    display: bool  # True si suffixe "d" → poser la question

_line = re.compile(r"""
    ^\s*
    (?P<key>[a-zA-Z_][a-zA-Z0-9_]*)
    \s*=\s*
    (?P<val>.+?)
    (?:\s+(?P<flag>d))?
    \s*$
""", re.VERBOSE)

def _coerce(s: str) -> Any:
    s = s.strip()
    if (len(s) >= 2) and ((s[0] == s[-1] == '"') or (s[0] == s[-1] == "'")):
        return s[1:-1]
    try:
        if "." in s:
            return float(s)
        return int(s)
    except ValueError:
        return s

def _ensure_options_file(path: str) -> None:
    """
    Si `path` (ex: options.conf) n'existe pas :
      - s'il existe `options.example.conf` au même endroit, on le copie.
      - sinon, on crée un fichier vide (ou minimal) pour démarrer.
    """
    if os.path.isfile(path):
        return

    example = os.path.join(os.path.dirname(path) or ".", "options.example.conf")
    try:
        if os.path.isfile(example):
            shutil.copyfile(example, path)
            print(f"[INFO] '{path}' introuvable : copie de '{example}'.")
        else:
            # Fallback minimal : créer un fichier vide (ou quelques valeurs commentées)
            with open(path, "w", encoding="utf-8") as f:
                f.write(
                    "# options.conf créé automatiquement.\n"
                    "# Exemple :\n"
                    "# voice_id = d\n"
                    "# audio_codec = \"ac3\"\n"
                    "# audio_bitrate = 256\n"
                    "# db = -5.0 d\n"
                    "# offset = 0 d\n"
                    "# bg = 1.0 d\n"
                    "# tts = 1.0 d\n"
                    "# orig_audio_lang = \"Original\" d\n"
                )
            print(f"[INFO] '{path}' introuvable : fichier minimal créé.")
    except Exception as e:
        print(f"[WARN] Impossible de préparer '{path}': {e}")

def load_options() -> Dict[str, OptEntry]:
    path = os.getenv("ADD_DUB_OPTIONS", "options.conf")
    _ensure_options_file(path)

    out: Dict[str, OptEntry] = {}
    if not os.path.isfile(path):
        return out

    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if not raw or raw.startswith("#") or raw.startswith(";"):
                continue
            m = _line.match(raw)
            if not m:
                continue
            key = m.group("key").strip().lower()
            val = _coerce(m.group("val"))
            display = (m.group("flag") or "").lower() == "d"
            out[key] = OptEntry(val, display)
    return out
