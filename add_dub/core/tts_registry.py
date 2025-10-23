# add_dub/core/tts_registry.py
"""
Façade/registre TTS moteur-agnostique.

- normalize_engine(value) -> "onecore" | "edge" | "gtts"
- list_voices_for_engine(engine) -> list[{"id","display_name","lang"}]
- is_valid_voice_for_engine(engine, voice_id) -> bool
- resolve_voice_with_fallbacks(engine, desired_voice_id, preferred_lang_base)
    → (1) voix exacte si valide
      (2) voix même langue+région pour le moteur choisi (si possible)
      (3) voix même langue (base) pour le moteur choisi (si possible)
      (4) voix par défaut système OneCore
      (5) None si rien trouvé
"""

from __future__ import annotations

from typing import List, Dict, Optional, Tuple
import locale


# --------------------------
# Normalisation moteur
# --------------------------
def normalize_engine(raw: str | None) -> str:
    if not raw:
        return "onecore"
    s = str(raw).strip().lower()
    if s in ("onecore", "edge", "gtts"):
        return s
    return "onecore"


# --------------------------
# OneCore (Windows)
# --------------------------
def _onecore_list_voices() -> List[Dict]:
    from add_dub.core.tts import list_available_voices as _list
    try:
        return _list()
    except Exception:
        return []


def _onecore_is_valid(voice_id: Optional[str]) -> bool:
    from add_dub.core.tts import is_valid_voice_id as _is_valid
    try:
        return _is_valid(voice_id)
    except Exception:
        return False


def _onecore_system_default() -> Optional[str]:
    from add_dub.core.tts import get_system_default_voice_id as _sysdef
    try:
        return _sysdef()
    except Exception:
        return None


# --------------------------
# Edge TTS
# --------------------------
def _edge_list_voices() -> List[Dict]:
    from add_dub.core.tts_edge import list_available_voices as _list
    try:
        return _list()
    except Exception:
        return []


def _edge_is_valid(voice_id: Optional[str]) -> bool:
    from add_dub.core.tts_edge import is_valid_voice_id as _is_valid
    try:
        return _is_valid(voice_id)
    except Exception:
        return False


# --------------------------
# gTTS
# --------------------------
def _gtts_list_voices() -> List[Dict]:
    from add_dub.core.tts_gtts import list_available_voices as _list
    try:
        return _list()
    except Exception:
        return []


def _gtts_is_valid(voice_id: Optional[str]) -> bool:
    from add_dub.core.tts_gtts import is_valid_voice_id as _is_valid
    try:
        return _is_valid(voice_id)
    except Exception:
        return False


# --------------------------
# Accès commun
# --------------------------
def list_voices_for_engine(engine: str) -> List[Dict]:
    eng = normalize_engine(engine)
    if eng == "edge":
        return _edge_list_voices()
    if eng == "gtts":
        return _gtts_list_voices()
    return _onecore_list_voices()


def is_valid_voice_for_engine(engine: str, voice_id: Optional[str]) -> bool:
    eng = normalize_engine(engine)
    if eng == "edge":
        return _edge_is_valid(voice_id)
    if eng == "gtts":
        return _gtts_is_valid(voice_id)
    return _onecore_is_valid(voice_id)


# --------------------------
# Helpers langue
# --------------------------
def _lang_base(tag: Optional[str]) -> str:
    if not tag:
        return ""
    t = tag.strip()
    if not t:
        return ""
    return t.split("-")[0].lower()


def _lang_full(tag: Optional[str]) -> Optional[str]:
    """
    Normalise un tag langue en 'll-rr' (ex: 'fr-fr') si possible.
    """
    if not tag:
        return None
    t = tag.strip().replace("_", "-").lower()
    parts = t.split("-")
    if len(parts) >= 2 and len(parts[0]) == 2 and len(parts[1]) == 2:
        return f"{parts[0]}-{parts[1]}"
    return None


def _lang_base_from_voice_id(voice_id: Optional[str]) -> Optional[str]:
    """
    Déduit une base de langue à partir de l'ID :
    - OneCore HKLM: extrait '_frFR_' -> 'fr'
    - Edge 'fr-FR-...' -> 'fr'
    - gTTS 'fr' -> 'fr'
    """
    if not voice_id:
        return None
    v = str(voice_id)
    # OneCore HKLM
    if "HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Speech_OneCore\\Voices\\Tokens\\" in v:
        import re
        m = re.search(r"_([a-z]{2})[A-Z]{2}_", v)
        if m:
            return m.group(1).lower()
        return None
    # Edge fr-FR-XXX
    if "-" in v:
        return v.split("-")[0].lower()
    # gTTS 'fr'
    if len(v) == 2:
        return v.lower()
    return None


def _system_locale() -> Tuple[Optional[str], Optional[str]]:
    """
    Retourne (lang_base, lang_full) de l'utilisateur Windows si possible,
    sinon via locale.getdefaultlocale().
    Exemples: ('fr', 'fr-fr'), ('en', 'en-us')
    """
    # Windows API (fiable pour l'UI user)
    try:
        import ctypes
        GetUserDefaultLocaleName = ctypes.windll.kernel32.GetUserDefaultLocaleName
        GetUserDefaultLocaleName.restype = ctypes.c_int
        buf = ctypes.create_unicode_buffer(85)
        if GetUserDefaultLocaleName(buf, 85) > 0:
            full = buf.value  # ex: 'fr-FR'
            full_norm = full.replace("_", "-").lower()
            parts = full_norm.split("-")
            base = parts[0] if parts else None
            if len(parts) >= 2:
                return base, f"{parts[0]}-{parts[1]}"
            return base, base
    except Exception:
        pass

    # Fallback générique Python
    try:
        loc = locale.getdefaultlocale()
        if loc and loc[0]:
            norm = loc[0].replace("_", "-").lower()
            parts = norm.split("-")
            base = parts[0] if parts else None
            full = f"{parts[0]}-{parts[1]}" if len(parts) >= 2 else base
            return base, full
    except Exception:
        pass

    return None, None


def _system_lang_base() -> Optional[str]:
    base, _full = _system_locale()
    return base


def _desired_lang_full(desired_voice_id: Optional[str]) -> Optional[str]:
    """
    Si l'utilisateur a donné 'fr-FR-XXX', renvoie 'fr-fr'.
    """
    if not desired_voice_id:
        return None
    v = desired_voice_id.replace("_", "-").lower()
    parts = v.split("-")
    if len(parts) >= 2 and len(parts[0]) == 2 and len(parts[1]) == 2:
        return f"{parts[0]}-{parts[1]}"
    return None


def _pick_by_lang_full_then_base(voices: List[Dict],
                                 prefer_full: Optional[str],
                                 prefer_base: Optional[str]) -> Optional[str]:
    """
    1) tente un match EXACT langue-région (ex: 'fr-fr')
    2) sinon, première voix qui matche la base langue (ex: 'fr-xx')
    """
    # 1) match exact
    if prefer_full:
        pf = prefer_full.lower()
        for v in voices:
            lang = (v.get("lang") or "").replace("_", "-").lower()
            if lang == pf:
                return v.get("id")

    # 2) match base
    if prefer_base:
        pb = prefer_base.lower()
        for v in voices:
            if _lang_base(v.get("lang")) == pb:
                return v.get("id")

    return None


# --------------------------
# Résolution principale
# --------------------------
def resolve_voice_with_fallbacks(
    *,
    engine: str,
    desired_voice_id: Optional[str],
    preferred_lang_base: Optional[str]
) -> Optional[str]:
    """
    Politique:
    1) Si desired_voice_id est valide pour ce moteur → OK.
    2) Sinon: tente une voix de même langue+région (voice_id / système),
       puis même langue (base).
    3) Sinon: prend la première voix dispo pour ce moteur.
    4) Sinon: fallback OneCore système.
    5) Sinon: None.
    """
    eng = normalize_engine(engine)

    # 1) Voix explicitement demandée et valide ?
    if desired_voice_id and is_valid_voice_for_engine(eng, desired_voice_id):
        return desired_voice_id

    # 2) Sélection par langue (full puis base)
    voices = list_voices_for_engine(eng)
    sys_base, sys_full = _system_locale()
    want_base = preferred_lang_base or _lang_base_from_voice_id(desired_voice_id) or sys_base
    want_full = _desired_lang_full(desired_voice_id) or sys_full
    pick = _pick_by_lang_full_then_base(voices, want_full, want_base)
    if pick:
        return pick

    # 3) Si moteur a des voix disponibles, prendre la première
    if voices:
        return voices[0]["id"]

    # 4) Fallback OneCore système
    sysdef = _onecore_system_default()
    if sysdef:
        return sysdef

    # 5) Rien
    return None
