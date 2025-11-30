# add_dub/config/effective.py
from __future__ import annotations

import os
from typing import Dict, Any

from add_dub.config import cfg
from add_dub.config.opts_loader import load_options
from add_dub.core.options import DubOptions
from add_dub.core.codecs import final_audio_codec_args, subtitle_codec_for_container


def _conf_value(opts: dict, key: str, fallback: Any) -> Any:
    """
    Récupère opts[key].value si présent, sinon fallback.
    """
    if key in opts:
        return opts[key].value
    return fallback


def _normalized_tts_engine(raw: str | None) -> str:
    """
    Normalise la valeur de tts_engine. None/"" => "onecore".
    """
    if not raw:
        return "onecore"
    s = str(raw).strip().lower()
    if s in ("onecore", "edge", "gtts"):
        return s
    # Valeur inconnue → fallback robuste
    return "onecore"


def effective_values(root: str | None = None) -> Dict[str, Any]:
    """
    Retourne les **valeurs scalaires effectives** (options.conf > defaults.py) destinées
    à être utilisées comme default= dans argparse et pour initialiser les répertoires.
    """
    if root:
        cwd = os.getcwd()
        try:
            os.chdir(root)
            opts = load_options()
        finally:
            os.chdir(cwd)
    else:
        opts = load_options()

    # defaults.py (cfg) comme fallback
    tts_engine = _normalized_tts_engine(_conf_value(opts, "tts_engine", getattr(cfg, "TTS_ENGINE", None)))
    voice = _conf_value(opts, "voice_id", getattr(cfg, "VOICE_ID", None))
    ducking_db = float(_conf_value(opts, "db", getattr(cfg, "DB_REDUCT", -5.0)))
    offset_ms = int(_conf_value(opts, "offset", getattr(cfg, "OFFSET_STR", 0)))
    offset_video_ms = int(_conf_value(opts, "offset_video", getattr(cfg, "OFFSET_VIDEO", 0)))
    bg_mix = float(_conf_value(opts, "bg", getattr(cfg, "BG_MIX", 1.0)))
    tts_mix = float(_conf_value(opts, "tts", getattr(cfg, "TTS_MIX", 1.0)))
    audio_codec = str(_conf_value(opts, "audio_codec", getattr(cfg, "AUDIO_CODEC_FINAL", "ac3")))
    audio_bitrate = int(_conf_value(opts, "audio_bitrate", getattr(cfg, "AUDIO_BITRATE", 320)))
    orig_audio_lang = str(_conf_value(opts, "orig_audio_lang", getattr(cfg, "ORIG_AUDIO_LANG", "Original")))
    min_rate_tts = float(_conf_value(opts, "min_rate_tts", getattr(cfg, "MIN_RATE_TTS", 1.0)))
    max_rate_tts = float(_conf_value(opts, "max_rate_tts", getattr(cfg, "MAX_RATE_TTS", 1.8)))
    ask_test_before_cleanup = bool(_conf_value(opts, "ask_test_before_cleanup", getattr(cfg, "ASK_TEST_BEFORE_CLEANUP", False)))
    translate = bool(_conf_value(opts, "translate", getattr(cfg, "TRANSLATE", False)))
    translate_to = str(_conf_value(opts, "translate_to", getattr(cfg, "TRANSLATE_TO", "fr")))

    # ↓↓↓ nouveaux (dirs)
    input_dir = str(_conf_value(opts, "input_dir", getattr(cfg, "INPUT_DIR", "input")))
    output_dir = str(_conf_value(opts, "output_dir", getattr(cfg, "OUTPUT_DIR", "output")))
    tmp_dir = str(_conf_value(opts, "tmp_dir", getattr(cfg, "TMP_DIR", "tmp")))
    # srt_dir est **fixe** côté io.fs (cfg.SRT_DIR), pas exposé ici
    language = str(_conf_value(opts, "language", getattr(cfg, "LANGUAGE", "auto")))

    return {
        "tts_engine": tts_engine,
        "voice": voice,
        "ducking_db": ducking_db,
        "offset_ms": offset_ms,
        "offset_video_ms": offset_video_ms,
        "bg_mix": bg_mix,
        "tts_mix": tts_mix,
        "audio_codec": audio_codec,
        "audio_bitrate": audio_bitrate,
        "orig_audio_lang": orig_audio_lang,
        "min_rate_tts": min_rate_tts,
        "max_rate_tts": max_rate_tts,
        "input_dir": input_dir,
        "output_dir": output_dir,
        "tmp_dir": tmp_dir,
        # --- NOUVEAU ---
        "ask_test_before_cleanup": ask_test_before_cleanup,
        "translate": translate,
        "translate_to": translate_to,
        "language": language,
    }


def build_default_opts() -> DubOptions:
    """
    Construit un DubOptions complet (logique interactive) : options.conf > defaults.py.
    Rappel important: on ne déclenche PLUS aucune question via 'voice_id d'.
    Seul 'tts_engine d' déclenchera plus tard un wizard moteur+voix dans la CLI.
    """
    opts = load_options()

    audio_codec = str(_conf_value(opts, "audio_codec", cfg.AUDIO_CODEC_FINAL))
    audio_bitrate = int(_conf_value(opts, "audio_bitrate", cfg.AUDIO_BITRATE))
    audio_args = final_audio_codec_args(audio_codec, f"{audio_bitrate}k")
    sub_codec = subtitle_codec_for_container(cfg.AUDIO_CODEC_FINAL)

    # Lecture simple (pas d'auto-display de voice_id ici)
    voice_id = _conf_value(opts, "voice_id", getattr(cfg, "VOICE_ID", None))
    tts_engine = _normalized_tts_engine(_conf_value(opts, "tts_engine", getattr(cfg, "TTS_ENGINE", None)))
    ask_test_before_cleanup = bool(_conf_value(opts, "ask_test_before_cleanup", getattr(cfg, "ASK_TEST_BEFORE_CLEANUP", False)))
    translate = bool(_conf_value(opts, "translate", getattr(cfg, "TRANSLATE", False)))
    translate_to = str(_conf_value(opts, "translate_to", getattr(cfg, "TRANSLATE_TO", "fr")))

    return DubOptions(
        audio_ffmpeg_index=None,
        sub_choice=None,
        orig_audio_lang=_conf_value(opts, "orig_audio_lang", cfg.ORIG_AUDIO_LANG),
        db_reduct=float(_conf_value(opts, "db", cfg.DB_REDUCT)),
        offset_ms=int(_conf_value(opts, "offset", cfg.OFFSET_STR)),
        bg_mix=float(_conf_value(opts, "bg", cfg.BG_MIX)),
        tts_mix=float(_conf_value(opts, "tts", cfg.TTS_MIX)),
        min_rate_tts=float(_conf_value(opts, "min_rate_tts", cfg.MIN_RATE_TTS)),
        max_rate_tts=float(_conf_value(opts, "max_rate_tts", cfg.MAX_RATE_TTS)),
        audio_codec=audio_codec,
        audio_bitrate=audio_bitrate,
        tts_engine=tts_engine,
        voice_id=voice_id,
        audio_codec_args=tuple(audio_args),
        sub_codec=sub_codec,
        offset_video_ms=int(_conf_value(opts, "offset_video", cfg.OFFSET_VIDEO)),
        # --- NOUVEAU ---
        ask_test_before_cleanup=ask_test_before_cleanup,
        translate=translate,
        translate_to=translate_to,
    )
