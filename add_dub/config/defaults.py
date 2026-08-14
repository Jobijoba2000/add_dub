# add_dub/config/defaults.py
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

# TTS
TTS_ENGINE = "onecore"
_default_voice_id = None

def get_voice_id_default() -> str | None:
    global _default_voice_id
    if _default_voice_id is None:
        _default_voice_id = get_system_default_voice_id()
    return _default_voice_id

# Propriété dynamique ou valeur par défaut
VOICE_ID = None
MIN_RATE_TTS = 1.0
MAX_RATE_TTS = 1.8
LANGUAGE = "auto"

# OUTPUT
AUDIO_CODEC_FINAL = "ac3"      # "aac", "mp3", "ac3", "flac", "opus", "vorbis", "pcm_s16le"
AUDIO_BITRATE = 320
BG_MIX = 1.0
TTS_MIX = 1.0

DB_REDUCT = -5.0
OFFSET_STR = 0                  # ms
OFFSET_VIDEO = 0                # ms
ORIG_AUDIO_LANG = "Original"

# DIRS
INPUT_DIR = "input"
OUTPUT_DIR = "output"
TMP_DIR = "tmp"
SRT_DIR = "srt"

# --- NOUVEAU ---
# Demander à l’utilisateur de tester la vidéo AVANT de supprimer les WAV temporaires,
# et permettre un re-mux rapide en ajustant bg/tts.
ASK_TEST_BEFORE_CLEANUP = False

# TRANSLATION
TRANSLATE = False
TRANSLATE_TO = "fr"
TRANSLATE_FROM = None
REUSE_TRANSLATED_SUBS = True

