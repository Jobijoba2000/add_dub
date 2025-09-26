# add_dub/config/opts_loader.py
from __future__ import annotations
import os, re
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

def load_options() -> Dict[str, OptEntry]:
    path = os.getenv("ADD_DUB_OPTIONS", "options.conf")
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
