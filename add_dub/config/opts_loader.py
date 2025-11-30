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
    low = s.lower()
    if low in ("true", "yes", "on", "1"):
        return True
    if low in ("false", "no", "off", "0"):
        return False
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
      - sinon, on crée un fichier minimal.
    """
    if os.path.isfile(path):
        return

    example = os.path.join(os.path.dirname(path) or ".", "options.example.conf")
    try:
        if os.path.isfile(example):
            shutil.copyfile(example, path)
            print(f"[INFO] '{path}' not found: copying '{example}'.")
        else:
            with open(path, "w", encoding="utf-8") as f:
                f.write(
                    "# options.conf\n"
                    "# language = auto\n"
                )
            print(f"[INFO] '{path}' not found: minimal file created.")
    except Exception as e:
        print(f"[WARN] Cannot prepare '{path}': {e}")

def load_options() -> Dict[str, OptEntry]:
    path = os.getenv("ADD_DUB_OPTIONS", "options.conf")
    _ensure_options_file(path)

    out: Dict[str, OptEntry] = {}
    if not os.path.isfile(path):
        return out

    current_section = ""

    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            # commentaires pleine ligne
            if line.startswith("#") or line.startswith(";"):
                continue
            # section [logging], etc.
            if line.startswith("[") and line.endswith("]"):
                current_section = line[1:-1].strip().lower()
                continue
            # commentaires inline ; et #
            line = line.split(";", 1)[0].split("#", 1)[0].strip()
            if not line:
                continue

            m = _line.match(line)
            if not m:
                continue

            key = m.group("key").strip().lower()
            if current_section:
                key = f"{current_section}.{key}"

            val = _coerce(m.group("val"))
            display = (m.group("flag") or "").lower() == "d"
            out[key] = OptEntry(val, display)
    return out
