# add_dub/cli/main.py

from dataclasses import dataclass
from typing import Callable, Any


@dataclass
class Services:
    resolve_srt_for_video: Callable[..., Any]
    generate_dub_audio: Callable[..., Any]
    choose_files: Callable[..., Any]
    choose_audio_track: Callable[..., Any]
    choose_subtitle_source: Callable[..., Any]

