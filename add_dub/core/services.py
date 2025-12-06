# add_dub/core/services.py

from dataclasses import dataclass
from typing import Callable, Any, Optional


from add_dub.core.ui import UIInterface

@dataclass
class Services:
    resolve_srt_for_video: Callable[..., Optional[str]]
    generate_dub_audio: Callable[..., str]
    choose_files: Callable[[list[str]], list[str]]
    choose_audio_track: Callable[[str], int]
    choose_subtitle_source: Callable[[str], Optional[str]]
    ui: UIInterface
