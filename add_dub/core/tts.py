# add_dub/core/tts.py
import os
import io
import uuid
import tempfile
import asyncio
from pydub import AudioSegment
import pyttsx3  # conservé pour les versions *_old

# OneCore (WinRT)
from winrt.windows.media.speechsynthesis import SpeechSynthesizer
from winrt.windows.storage.streams import DataReader


# ---------------------------
# Helpers OneCore (internes)
# ---------------------------

def _normalize_rate(rate):
    """
    OneCore uniquement : facteur de vitesse (1.0 = normal).
    On borne dans [1.0, 1.8]. Valeur invalide → 1.0.
    """
    try:
        r = float(rate)
    except (TypeError, ValueError):
        return 1.0
    return max(1.0, min(1.8, r))



def _pick_voice_obj(voice_id: str | None):
    voices = list(SpeechSynthesizer.all_voices)
    if not voices:
        return None
    if voice_id:
        # Match direct par id exact, sinon par fragment dans display_name
        for v in voices:
            if v.id == voice_id:
                return v
        low = voice_id.lower()
        for v in voices:
            if low in (v.display_name or "").lower():
                return v
    # défaut : première voix
    return voices[0]


async def _onecore_synthesize_bytes_async(text: str, voice_id: str | None, rate_factor: float) -> bytes:
    synth = SpeechSynthesizer()
    v = _pick_voice_obj(voice_id)
    if v is not None:
        synth.voice = v
    # speaking_rate dispo via options
    try:
        synth.options.speaking_rate = rate_factor
    except Exception:
        # si indispo sur cette build, on ignore
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
    data = asyncio.run(_onecore_synthesize_bytes_async(text, voice_id, rate_factor))
    bio = io.BytesIO(data)
    return AudioSegment.from_file(bio, format="wav")


# ------------------------------------------------
# Implémentations OneCore (remplacent les anciennes)
# ------------------------------------------------

def get_tts_duration_for_rate(text, rate, voice_id=None):
    """
    Synthèse OneCore à un débit donné (factor), retourne durée en ms.
    """
    factor = _normalize_rate(rate)
    segment = _onecore_synthesize_segment(text, voice_id, factor)
    return len(segment)


def find_optimal_rate(text, target_duration_ms, voice_id=None):
    """
    Cherche un facteur OneCore tel que la durée synthétisée ≈ target_duration_ms.
    Recherche binaire simple sur [0.5, 2.5].
    """
    if not text:
        return 1.0

    low, high = 0.5, 2.5
    best = 1.0
    best_err = float("inf")

    for _ in range(10):  # 10 itérations suffisent en pratique
        mid = (low + high) / 2.0
        dur = get_tts_duration_for_rate(text, mid, voice_id)
        err = abs(dur - target_duration_ms)
        if err < best_err:
            best, best_err = mid, err
        if err <= 80:  # tolérance ~80 ms
            return mid
        # Si c'est trop long, on accélère (↑ rate) ; si trop court, on ralentit (↓ rate)
        if dur > target_duration_ms:
            low = mid  # besoin plus rapide → facteur plus grand
        else:
            high = mid
    return best


def synthesize_tts_for_subtitle(text, target_duration_ms, voice_id=None):
    """
    Synthèse OneCore ajustée à la durée cible.
    Retourne un AudioSegment (coupé/paddé à target_duration_ms).
    """
    factor = find_optimal_rate(text, target_duration_ms, voice_id)
    segment = _onecore_synthesize_segment(text, voice_id, factor)

    # Ajustement exact à la durée cible (comme avant)
    cur = len(segment)
    if cur > target_duration_ms:
        segment = segment[:target_duration_ms]
    elif cur < target_duration_ms:
        segment = segment + AudioSegment.silent(duration=(target_duration_ms - cur))
    return segment


# ------------------------------------------------
# Versions d'origine basées sur pyttsx3 (suffixe _old)
# ------------------------------------------------

def get_tts_duration_for_rate_old(text, rate, voice_id=None):
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
