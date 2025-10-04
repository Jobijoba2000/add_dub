# add_dub/core/tts.py
import os
import io
import uuid
import tempfile
import asyncio
from pydub import AudioSegment

# Typage (et pour accéder aux bornes min/max depuis l'instance)
from add_dub.core.options import DubOptions

# OneCore (WinRT)
try:
    from winrt.windows.media.speechsynthesis import SpeechSynthesizer
    from winrt.windows.storage.streams import DataReader
except Exception:
    SpeechSynthesizer = None
    DataReader = None


# --------------------------------
# Listing des voix OneCore
# --------------------------------

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

def _normalize_rate(rate: float, *, opts: DubOptions) -> float:
    """
    OneCore uniquement : facteur de vitesse (1.0 = normal).
    Borne dans [opts.min_rate_tts, opts.max_rate_tts]. Valeur invalide → opts.min_rate_tts.
    """
    try:
        r = float(rate)
    except (TypeError, ValueError):
        return opts.min_rate_tts
    return max(opts.min_rate_tts, min(opts.max_rate_tts, r))


def _pick_voice_obj(voice_id: str | None):
    """
    Sélection STRICTE (aucun garde-fou ici) :
      - si voice_id est fourni: match exact d'ID uniquement, sinon None.
      - si voice_id est None: None.
    Les contrôles amont (is_valid_voice_id / defaults / build_default_opts) garantissent
    normalement un ID valide avant d'arriver jusqu'ici.
    """
    if SpeechSynthesizer is None:
        return None
    try:
        voices = list(SpeechSynthesizer.all_voices)
    except Exception:
        return None

    if not voice_id:
        return None

    vid = voice_id.strip()
    for v in voices:
        if getattr(v, "id", "") == vid:
            return v
    return None


async def _onecore_synthesize_bytes_async(text: str, voice_id: str | None, rate_factor: float) -> bytes:
    """
    AUCUN fallback ici :
      - WinRT indisponible → RuntimeError
      - voice_id introuvable → RuntimeError
    """
    if SpeechSynthesizer is None or DataReader is None:
        raise RuntimeError("No TTS voice available (WinRT SpeechSynthesizer not available)")

    synth = SpeechSynthesizer()
    v = _pick_voice_obj(voice_id)
    if v is None:
        raise RuntimeError("No TTS voice available (requested voice id not found)")

    synth.voice = v
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


def _onecore_synthesize_segment(text: str, voice_id: str | None, rate_factor: float) -> AudioSegment:
    """
    Laisse remonter les erreurs (pas de segment silencieux masquant le problème).
    """
    data = asyncio.run(_onecore_synthesize_bytes_async(text, voice_id, rate_factor))
    bio = io.BytesIO(data)
    return AudioSegment.from_file(bio, format="wav")


# ------------------------------------------------
# Implémentations OneCore
# ------------------------------------------------

def get_tts_duration_for_rate(text: str, rate: float, voice_id: str | None, opts: DubOptions) -> int:
    """
    Synthèse OneCore à un débit donné (factor), retourne durée en ms.
    """
    factor = _normalize_rate(rate, opts=opts)
    segment = _onecore_synthesize_segment(text, voice_id, factor)
    return len(segment)


def find_optimal_rate(text: str, target_duration_ms: int, voice_id: str | None, opts: DubOptions) -> float:
    """
    Cherche un facteur OneCore tel que la durée synthétisée ≈ target_duration_ms.
    Recherche binaire simple sur [0.5, 2.5], borné ensuite par opts.
    """
    if not text:
        return 1.0

    low, high = 0.5, 2.5
    best = 1.0
    best_err = float("inf")

    for _ in range(10):
        mid = (low + high) / 2.0
        dur = get_tts_duration_for_rate(text, mid, voice_id, opts)
        err = abs(dur - target_duration_ms)
        if err < best_err:
            best, best_err = mid, err
        if err <= 80:
            # on renvoie une valeur normalisée dans les bornes opts
            return _normalize_rate(mid, opts=opts)
        if dur > target_duration_ms:
            low = mid
        else:
            high = mid

    return _normalize_rate(best, opts=opts)


def synthesize_tts_for_subtitle(text: str, target_duration_ms: int, voice_id: str | None, opts: DubOptions) -> AudioSegment:
    """
    Synthèse OneCore ajustée à la durée cible.
    Retourne un AudioSegment (coupé/paddé à target_duration_ms).
    """
    factor = find_optimal_rate(text, target_duration_ms, voice_id, opts)
    segment = _onecore_synthesize_segment(text, voice_id, factor)

    cur = len(segment)
    if cur > target_duration_ms:
        segment = segment[:target_duration_ms]
    elif cur < target_duration_ms:
        segment = segment + AudioSegment.silent(duration=(target_duration_ms - cur))
    return segment


# ------------------------------------------------
# Anciennes versions pyttsx3 (_old) — laissées pour compatibilité
# ------------------------------------------------

def get_tts_duration_for_rate_old(text, rate, voice_id=None):
    import pyttsx3
    engine = pyttsx3.init()
    if voice_id:
        engine.setProperty("voice", voice_id)
    engine.setProperty("rate", rate)
    temp_file = os.path.join(tempfile.gettempdir(), "tts_temp_" + str(uuid.uuid4()) + ".wav")
    engine.save_to_file(text, temp_file)
    engine.runAndWait()
    if os.path.exists(temp_file):
        segment = AudioSegment.from_file(temp_file)
        duration = len(segment)
        try:
            os.remove(temp_file)
        except Exception:
            pass
    else:
        duration = 0
    engine.stop()
    return duration


def find_optimal_rate_old(text, target_duration_ms, voice_id=None):
    low, high = 200, 360
    candidate = None
    while low <= high:
        mid = (low + high) // 2
        current_duration = get_tts_duration_for_rate_old(text, mid, voice_id)
        if abs(current_duration - target_duration_ms) <= 100:
            candidate = mid
            break
        if current_duration < target_duration_ms:
            candidate = mid
            high = mid - 10
        else:
            low = mid + 10
    if candidate is None:
        candidate = 200
    return candidate


def synthesize_tts_for_subtitle_old(text, target_duration_ms, voice_id=None):
    import pyttsx3
    optimal_rate = find_optimal_rate_old(text, target_duration_ms, voice_id)
    engine = pyttsx3.init()
    if voice_id:
        engine.setProperty("voice", voice_id)
    engine.setProperty("rate", optimal_rate)
    temp_file = os.path.join(tempfile.gettempdir(), "tts_temp_" + str(uuid.uuid4()) + ".wav")
    engine.save_to_file(text, temp_file)
    engine.runAndWait()
    if os.path.exists(temp_file):
        segment = AudioSegment.from_file(temp_file)
    else:
        segment = AudioSegment.silent(duration=0)
    try:
        if os.path.exists(temp_file):
            os.remove(temp_file)
    except Exception:
        pass
    engine.stop()
    if len(segment) > target_duration_ms:
        segment = segment[:target_duration_ms]
    elif len(segment) < target_duration_ms:
        segment = segment + AudioSegment.silent(duration=(target_duration_ms - len(segment)))
    return segment


def get_system_default_voice_id() -> str | None:
    """
    Retourne l'ID complet (OneCore) de la voix TTS par défaut du système.
    - Si la voix par défaut est accessible: retourne son .id
    - Sinon: retourne l'ID de la première voix disponible
    - Si aucune voix/WinRT indisponible: retourne None
    """
    try:
        from winrt.windows.media.speechsynthesis import SpeechSynthesizer  # type: ignore
    except Exception:
        return None

    try:
        synth = SpeechSynthesizer()
        v = getattr(synth, "voice", None)
        if v:
            vid = getattr(v, "id", "") or ""
            if vid:
                return vid
    except Exception:
        pass

    try:
        voices = list(SpeechSynthesizer.all_voices)
        if voices:
            vid = getattr(voices[0], "id", "") or ""
            return vid or None
    except Exception:
        pass

    return None


def is_valid_voice_id(voice_id: str | None) -> bool:
    """
    True si voice_id correspond exactement à une voix OneCore installée.
    False si None, vide, WinRT indisponible, ou ID introuvable.
    Affiche un avertissement si une valeur non vide (ex: depuis options.conf) est invalide.
    """
    if not voice_id:
        # Absence de valeur: pas d'avertissement ici.
        print("pas de voice_id")
        return False

    if SpeechSynthesizer is None:
        print("[WARN] WinRT/SpeechSynthesizer indisponible : impossible de valider 'voice_id' défini dans options.conf.")
        return False

    try:
        voices = list(SpeechSynthesizer.all_voices)
    except Exception:
        print("[WARN] Impossible d'énumérer les voix OneCore : validation de 'voice_id' (options.conf) non réalisée.")
        return False

    vid = str(voice_id).strip()
    for v in voices:
        if getattr(v, "id", "") == vid:
            return True

    # Valeur non vide mais introuvable → avertissement explicite
    print(f"[WARN] 'voice_id' invalide dans options.conf : '{vid}'. Voix introuvable sur ce système.")
    return False
