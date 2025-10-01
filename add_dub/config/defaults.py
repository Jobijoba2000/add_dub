# add_dub/config/defaults.py
from add_dub.core.tts import get_system_default_voice_id

VOICE_ID = get_system_default_voice_id()
ORIG_AUDIO_LANG = "Original"
AUDIO_CODEC_FINAL = "ac3"      # "aac", "mp3", "ac3", "flac", "opus", "vorbis", "pcm_s16le"
AUDIO_BITRATE = 320         # ex: "192k" ou None
BG_MIX = 1.0                   # niveau BG
TTS_MIX = 1.0                  # niveau TTS
DB_REDUCT = -5.0               # ducking en dB
OFFSET_STR = 0                 # ms

