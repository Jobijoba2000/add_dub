# add_dub/core/tts.py
import os
import io
import uuid
import tempfile
import asyncio
from pydub import AudioSegment
from add_dub.config.defaults import get_system_default_voice_id  # re-export

# Typage (et pour accéder aux bornes min/max depuis l'instance)
from add_dub.core.options import DubOptions
from add_dub.logger import (log_call, log_time)
from add_dub.i18n import t
import time

# OneCore (WinRT)
try:
    from winrt.windows.media.speechsynthesis import SpeechSynthesizer
    from winrt.windows.storage.streams import DataReader
except Exception:
    SpeechSynthesizer = None
    DataReader = None


# --------------------------------
# Caches par processus (memoization locale à chaque worker)
# --------------------------------
_SYNTH = None          # instance unique du synthétiseur OneCore (par process)
_VOICE_LIST = None     # liste des voix OneCore (par process)
_VOICE_OBJ = None      # objet voix résolu pour la voice_id courante (par process)
_CURRENT_VOICE_ID = None  # voice_id actuellement résolue dans _VOICE_OBJ


def _get_synth():
    """
    Retourne un synthétiseur OneCore unique par processus.
    Créé paresseusement à la première utilisation.
    """
    global _SYNTH
    if _SYNTH is None and SpeechSynthesizer is not None:
        _SYNTH = SpeechSynthesizer()
    return _SYNTH

def _get_voice_list():
    """
    Charge une fois la liste des voix OneCore dans le process courant.
    """
    global _VOICE_LIST
    if _VOICE_LIST is None:
        if SpeechSynthesizer is None:
            _VOICE_LIST = []
        else:
            try:
                _VOICE_LIST = list(SpeechSynthesizer.all_voices)
            except Exception:
                _VOICE_LIST = []
    return _VOICE_LIST

def _get_voice_obj_from_id(voice_id: str | None):
    """
    Résout (et mémorise) l'objet voix à partir d'un voice_id connu/valide.
    Ne rescane pas les voix si la voice_id ne change pas.
    """
    global _VOICE_OBJ, _CURRENT_VOICE_ID
    if SpeechSynthesizer is None or not voice_id:
        return None

    vid = voice_id.strip()
    if _CURRENT_VOICE_ID == vid and _VOICE_OBJ is not None:
        return _VOICE_OBJ

    voices = _get_voice_list()
    for v in voices:
        if getattr(v, "id", "") == vid:
            _VOICE_OBJ = v
            _CURRENT_VOICE_ID = vid
            return _VOICE_OBJ

    # Non trouvé
    _VOICE_OBJ = None
    _CURRENT_VOICE_ID = None
    return None

def list_available_voices() -> list[dict]:
    """
    Retourne la liste des voix OneCore sous forme de dictionnaires:
        [{ "id": str, "display_name": str, "lang": str }, ...]
    - id : l'ID complet OneCore (copiable tel quel dans options.conf)
    - display_name : nom lisible (ex. 'Microsoft Julie')
    - lang : tag BCP-47 (ex. 'fr-FR', 'es-ES')
    """
    out: list[dict] = []
    if SpeechSynthesizer is None:
        return out
    try:
        voices = list(SpeechSynthesizer.all_voices)
    except Exception:
        voices = []
    for v in voices:
        vid = getattr(v, "id", "") or ""
        dname = getattr(v, "display_name", "") or ""
        lang = getattr(v, "language", "") or ""
        out.append({"id": vid, "display_name": dname, "lang": lang})
    return out


# ---------------------------
# Helpers OneCore (internes)
# ---------------------------

def _pick_voice_obj(voice_id: str | None):
    """
    Sélection STRICTE (aucun garde-fou ici) :
      - si voice_id est fourni: match exact d'ID uniquement, sinon None.
      - si voice_id est None: None.
    Les contrôles amont (is_valid_voice_id / defaults / build_default_opts) garantissent
    normalement un ID valide avant d'arriver jusqu'ici.

    Implémentation mémorisée : n'énumère pas les voix à chaque appel si la voice_id ne change pas.
    """
    if SpeechSynthesizer is None:
        return None
    if not voice_id:
        return None
    return _get_voice_obj_from_id(voice_id)

async def _onecore_synthesize_bytes_async(text: str, voice_id: str | None, rate_factor: float) -> bytes:
    """
    AUCUN fallback ici :
      - WinRT indisponible → RuntimeError
      - voice_id introuvable → RuntimeError
    """
    if SpeechSynthesizer is None or DataReader is None:
        raise RuntimeError("No TTS voice available (WinRT SpeechSynthesizer not available)")

    synth = _get_synth()
    if synth is None:
        raise RuntimeError("No TTS voice available (synthesizer not created)")

    v = _pick_voice_obj(voice_id)
    if v is None:
        raise RuntimeError("No TTS voice available (requested voice id not found)")

    # Assigner la voix uniquement si nécessaire
    try:
        if getattr(synth.voice, "id", None) != getattr(v, "id", None):
            synth.voice = v
    except Exception:
        synth.voice = v

    # Régler le débit (peut ne pas être dispo selon build)
    try:
        synth.options.speaking_rate = rate_factor
    except Exception:
        pass

    stream = await synth.synthesize_text_to_stream_async(text)

    size = int(stream.size)
    input_stream = stream.get_input_stream_at(0)
    reader = DataReader(input_stream)
    await reader.load_async(size)
    buf = bytearray(size)
    reader.read_bytes(buf)
    return bytes(buf)


def _onecore_synthesize_segment(
    text: str,
    target_duration_ms: int,
    voice_id: str | None, 
    opts
) -> AudioSegment:
    """
    Laisse remonter les erreurs (pas de segment silencieux masquant le problème).
    """
    r = opts.min_rate_tts
    h = opts.max_rate_tts
    t = target_duration_ms
    v = opts.voice_id
    for _ in range(10):
        data    = asyncio.run(_onecore_synthesize_bytes_async(text, v, r))
        bio     = io.BytesIO(data)
        segment = AudioSegment.from_file(bio, format="wav")
        if len(segment) <= t or r >= h:
            return segment
        else:
            r = ((r * 10) + 1) / 10
    return segment

def synthesize_tts_for_subtitle(text: str, target_duration_ms: int, voice_id: str | None, opts: DubOptions) -> AudioSegment:
    """
    Synthèse OneCore ajustée à la durée cible.
    Retourne un AudioSegment (coupé/paddé à target_duration_ms).
    """
    segment = _onecore_synthesize_segment(
        text, 
        target_duration_ms, 
        voice_id, 
        opts
    )

    cur = len(segment)
    if cur > target_duration_ms:
        segment = segment[:target_duration_ms]
    elif cur < target_duration_ms:
        segment = segment + AudioSegment.silent(duration=(target_duration_ms - cur))
    return segment

def is_valid_voice_id(voice_id: str | None) -> bool:
    """
    True si voice_id correspond exactement à une voix OneCore installée.
    False si None, vide, WinRT indisponible, ou ID introuvable.
    Affiche un avertissement si une valeur non vide (ex: depuis options.conf) est invalide.
    """
    if not voice_id:
        return True

    if SpeechSynthesizer is None:
        print(t("tts_warn_winrt_unavailable"))
        return True

    voices = _get_voice_list()
    if not voices:
        print(t("tts_warn_enum_fail"))
        return True

    vid = str(voice_id).strip()
    found = False
    for v in voices:
        v_id = getattr(v, "id", "")
        if vid == v_id:
            found = True
            break
    
    if not found:
        print(t("tts_warn_invalid_voiceid", vid=vid))
        return False
    return True
