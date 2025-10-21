# add_dub/core/tts_registry.py
"""
Façade/registre TTS moteur-agnostique.

- normalize_engine(value) -> "onecore" | "edge" | "gtts"
- list_voices_for_engine(engine) -> list[{"id","display_name","lang"}]
- is_valid_voice_for_engine(engine, voice_id) -> bool
- resolve_voice_with_fallbacks(engine, desired_voice_id, preferred_lang_base)
    → (1) voix exacte si valide
      (2) voix même langue pour le moteur choisi (si possible)
      (3) voix par défaut système OneCore
      (4) None si rien trouvé
"""

from __future__ import annotations

from typing import List, Dict, Optional


def normalize_engine(raw: str | None) -> str:
    if not raw:
        return "onecore"
    s = str(raw).strip().lower()
    if s in ("onecore", "edge", "gtts"):
        return s
    return "onecore"


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


def _lang_base(tag: str | None) -> str:
    if not tag:
        return ""
    t = tag.strip()
    if not t:
        return ""
    return t.split("-")[0].lower()


def _pick_first_same_lang(voices: List[Dict], preferred_lang_base: Optional[str]) -> Optional[str]:
    if not voices or not preferred_lang_base:
        return None
    b = preferred_lang_base.strip().lower()
    # Cherche d'abord même base exacte, ensuite première voix dispo
    for v in voices:
        if _lang_base(v.get("lang")) == b:
            return v.get("id")
    return None


def resolve_voice_with_fallbacks(
    *,
    engine: str,
    desired_voice_id: Optional[str],
    preferred_lang_base: Optional[str]
) -> Optional[str]:
    """
    1) Si desired_voice_id est valide pour ce moteur → OK.
    2) Sinon: tente une voix de même langue sur ce moteur.
    3) Sinon: voix système par défaut OneCore.
    4) Sinon: None.
    """
    eng = normalize_engine(engine)

    # 1) Voix prévue valide ?
    if desired_voice_id and is_valid_voice_for_engine(eng, desired_voice_id):
        return desired_voice_id

    # 2) Essayer même langue (si fournie)
    voices = list_voices_for_engine(eng)
    pick = _pick_first_same_lang(voices, preferred_lang_base)
    if pick:
        return pick

    # 3) Fallback OneCore système
    sysdef = _onecore_system_default()
    if sysdef:
        return sysdef

    # 4) Rien
    return None
