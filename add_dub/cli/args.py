# add_dub/cli/args.py
from __future__ import annotations

import argparse
import re
from typing import Tuple, List

from add_dub.config.effective import effective_values
from add_dub.i18n import t, init_language


def parse_args(argv: List[str]) -> Tuple[argparse.Namespace, List[str]]:
    """
    Les defaults d'argparse viennent du builder partagé (options.conf > defaults.py).
    Si l'utilisateur ne passe pas un flag, il récupère ces valeurs "effectives".
    """
    fused = effective_values()
    init_language()

    parser = argparse.ArgumentParser(
        prog="add_dub",
        description=t("help_desc")
    )

    # Modes
    g_mode = parser.add_mutually_exclusive_group()
    g_mode.add_argument("--interactive", action="store_true", help=t("help_interactive"))
    g_mode.add_argument("--batch", action="store_true", help=t("help_batch"))

    # --- Groupes d'arguments pour plus de clarté ---
    
    # 1. Input / Output
    g_io = parser.add_argument_group(t("grp_io"))
    g_io.add_argument("--input", "-i", nargs="+", metavar="PATH", help=t("help_input"))
    g_io.add_argument("--output-dir", metavar="PATH", default=None, help=t("help_output_dir"))
    g_io.add_argument("--recursive", "-r", action="store_true", help=t("help_recursive"))
    g_io.add_argument("--overwrite", action="store_true", help=t("help_overwrite"))
    g_io.add_argument("--dry-run", action="store_true", help=t("help_dry_run"))

    # 2. Audio Configuration
    g_audio = parser.add_argument_group(t("grp_audio"))
    g_audio.add_argument("--tts-engine", choices=["onecore", "edge", "gtts"], default=fused["tts_engine"], help=t("help_tts_engine"))
    g_audio.add_argument("--voice", metavar="ID", default=fused["voice"], help=t("help_voice"))
    g_audio.add_argument("--audio-index", type=int, metavar="IDX", default=None, help=t("help_audio_index"))
    g_audio.add_argument("--audio-codec", metavar="CODEC", default=fused["audio_codec"], 
                         choices=["ac3", "aac", "libopus", "opus", "flac", "libvorbis", "vorbis", "pcm_s16le"],
                         help=t("help_audio_codec"))
    g_audio.add_argument("--audio-bitrate", type=int, metavar="KBPS", default=fused["audio_bitrate"], help=t("help_audio_bitrate"))

    # 3. Subtitles
    g_sub = parser.add_argument_group(t("grp_sub"))
    g_sub.add_argument("--sub", metavar="SRC", default="auto", help=t("help_sub"))

    # 4. Translation
    g_trans = parser.add_argument_group(t("grp_trans"))
    g_trans.add_argument("--translate", action="store_true", help=t("help_translate"))
    g_trans.add_argument("--translate-to", metavar="LANG", default=fused["translate_to"], help=t("help_translate_to"))
    g_trans.add_argument("--translate-from", metavar="LANG", default=None, help=t("help_translate_from"))

    # 5. Mixing & Timing (Advanced)
    g_mix = parser.add_argument_group(t("grp_mix"))
    g_mix.add_argument("--ducking-db", type=float, metavar="DB", default=fused["ducking_db"], help=t("help_ducking_db"))
    g_mix.add_argument("--bg-mix", type=float, metavar="VOL", default=fused["bg_mix"], help=t("help_bg_mix"))
    g_mix.add_argument("--tts-mix", type=float, metavar="VOL", default=fused["tts_mix"], help=t("help_tts_mix"))
    g_mix.add_argument("--offset-ms", type=int, metavar="MS", default=fused["offset_ms"], help=t("help_offset_ms"))
    g_mix.add_argument("--offset-video-ms", type=int, metavar="MS", default=fused["offset_video_ms"], help=t("help_offset_video_ms"))
    g_mix.add_argument("--min-rate-tts", type=float, metavar="RATE", default=fused["min_rate_tts"], help=t("help_min_rate_tts"))
    g_mix.add_argument("--max-rate-tts", type=float, metavar="RATE", default=fused["max_rate_tts"], help=t("help_max_rate_tts"))
    g_mix.add_argument("--limit-duration-sec", type=int, metavar="SEC", default=None, help=t("help_limit_duration"))

    args, unknown = parser.parse_known_args(argv)

    # Normalisation de --sub en sub_mode + sub_index
    raw = (getattr(args, "sub", "auto") or "auto").strip().lower()
    sub_mode = "auto"
    sub_index = 0
    m = re.match(r"^(mkv)\s*[:=]\s*(\d+)$", raw)
    if m:
        sub_mode = "mkv"
        sub_index = int(m.group(2))
    elif raw in ("auto", "srt", "mkv"):
        sub_mode = raw
    else:
        sub_mode = "auto"
        sub_index = 0

    args.sub_mode = sub_mode
    args.sub_index = sub_index

    return args, unknown


def want_interactive(args: argparse.Namespace) -> bool:
    """
    Décide si on doit lancer l'interactif.
    - Interactif si --interactive
    - Interactif si rien n'est précisé
    - Batch si --batch
    """
    if getattr(args, "batch", False):
        return False
    return True
