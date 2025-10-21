# add_dub/core/options.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Iterable, Tuple


@dataclass
class DubOptions:
    """
    Options de configuration transmises à travers tout le pipeline.
    Isolée dans un module neutre pour éviter les imports circulaires.
    """
    audio_ffmpeg_index: Optional[int] = None          # index de la piste source (ffmpeg)
    sub_choice: Optional[tuple] = None                # ("srt", path) ou ("mkv", idx)
    orig_audio_lang: Optional[str] = None             # libellé de la piste originale dans la sortie
    db_reduct: float = -5.0                           # ducking en dB
    offset_ms: int = 0                                # décalage ST/TTS
    bg_mix: float = 1.0                               # gain BG
    tts_mix: float = 1.0                              # gain TTS
    min_rate_tts: float = 1.0                         # borne basse TTS
    max_rate_tts: float = 1.8                         # borne haute TTS
    audio_codec: str = "ac3"                          # codec audio final
    audio_bitrate: int = 320                          # bitrate audio final (kb/s)
    tts_engine: Optional[str] = None
    voice_id: Optional[str] = None                    # identifiant de voix (OneCore, etc.)
    audio_codec_args: Iterable[str] = ()              # args ffmpeg audio final (ex: "-c:a","aac","-b:a","192k")
    sub_codec: str = "srt"                            # "srt" ou "ass"
    offset_video_ms: int = 0                          # décalage piste vidéo

__all__ = ["DubOptions", "Services"]
