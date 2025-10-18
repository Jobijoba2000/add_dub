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


VOICE_ID = get_system_default_voice_id()
ORIG_AUDIO_LANG = "Original"
AUDIO_CODEC_FINAL = "ac3"      # "aac", "mp3", "ac3", "flac", "opus", "vorbis", "pcm_s16le"
AUDIO_BITRATE = 320
BG_MIX = 1.0
TTS_MIX = 1.0
MIN_RATE_TTS = 1.0
MAX_RATE_TTS = 2.8
DB_REDUCT = -5.0
OFFSET_STR = 0                  # ms
OFFSET_VIDEO = 0                # ms

# ↓↓↓ nouveaux défauts dossiers (peuvent être surchargés par options.conf)
INPUT_DIR = "input"
OUTPUT_DIR = "output"
TMP_DIR = "tmp"

# Dossier SRT **fixe** (non configurable)
SRT_DIR = "srt"
