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


def save_option(key: str, value: Any, display: bool | None = None) -> None:
    """
    Met à jour une option dans options.conf en préservant les commentaires et la structure.
    Si la clé n'existe pas, elle n'est PAS ajoutée (pour l'instant, on suppose qu'elle existe).
    """
    path = os.getenv("ADD_DUB_OPTIONS", "options.conf")
    if not os.path.isfile(path):
        return

    # Préparation de la valeur string
    if isinstance(value, bool):
        val_str = "true" if value else "false"
    else:
        val_str = str(value)

    # Lecture complète
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    new_lines = []
    key_lower = key.lower()
    
    # Gestion des sections (simple: on ignore la section pour la recherche de clé unique pour l'instant,
    # ou on suppose que les clés sont uniques globalement comme dans le loader actuel)
    # Le loader actuel préfixe par section si section présente.
    # Ici on va faire une recherche simple ligne par ligne.
    
    current_section = ""
    updated = False

    for line in lines:
        raw_line = line.strip()
        if raw_line.startswith("[") and raw_line.endswith("]"):
            current_section = raw_line[1:-1].strip().lower()
            new_lines.append(line)
            continue
            
        if not raw_line or raw_line.startswith("#") or raw_line.startswith(";"):
            new_lines.append(line)
            continue

        # Check key
        # On doit parser la ligne pour voir si c'est la bonne clé
        # On réutilise la regex _line mais attention elle capture flag
        m = _line.match(raw_line)
        if m:
            found_key = m.group("key").strip().lower()
            if current_section:
                found_key = f"{current_section}.{found_key}"
            
            if found_key == key_lower:
                # C'est la ligne à modifier
                # On reconstruit la ligne
                # On garde l'indentation originale si possible (souvent 0)
                indent = line[:line.find(m.group("key"))]
                
                # Récupérer l'ancien flag si display est None
                old_flag = m.group("flag") or ""
                new_flag_str = ""
                
                if display is True:
                    new_flag_str = " d"
                elif display is False:
                    new_flag_str = ""
                else:
                    # None => on garde l'ancien
                    if old_flag.lower() == "d":
                        new_flag_str = " d"
                
                # On écrit la nouvelle ligne
                # Format: key = value [d]
                # On essaie de garder le style
                new_line = f"{indent}{m.group('key')} = {val_str}{new_flag_str}\n"
                new_lines.append(new_line)
                updated = True
                continue

        new_lines.append(line)

    with open(path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
