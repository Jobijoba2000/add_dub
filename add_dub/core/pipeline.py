# add_dub/core/pipeline.py

import os
import subprocess
import time
from dataclasses import dataclass
from typing import Callable, Optional, Iterable

from pydub import AudioSegment

from add_dub.io.fs import join_input, join_output
from add_dub.core.subtitles import parse_srt_file, strip_subtitle_tags_inplace
from add_dub.core.ducking import lower_audio_during_subtitles
from add_dub.adapters.ffmpeg import (
    extract_audio_track,
    mix_audios,
    encode_original_audio_to_final_codec,
    merge_to_container,
)
from add_dub.helpers.time import measure_duration as _md
import re

def _dub_code_from_voice(voice_id: str | None) -> str:
    from add_dub.core.tts import list_available_voices
    if not voice_id:
        return "fr"
    try:
        voices = list_available_voices()
    except Exception:
        voices = []
    lang = ""
    vid = str(voice_id).strip()
    for v in voices:
        if str(v.get("id", "")).strip() == vid:
            lang = (v.get("lang") or "").strip()
            break
    if not lang:
        m = re.search(r"([a-zA-Z]{2})(?:[-_][A-Za-z]{2})?", vid)
        if m:
            lang = m.group(0)
    base = (lang.split("-")[0] if lang else "fr").lower()
    return re.sub(r"[^a-z]", "", base) or "fr"

def _step(msg: str) -> None:
    print("\n" + msg)

@dataclass
class DubOptions:
    audio_ffmpeg_index: Optional[int] = None          # index de la piste source (ffmpeg)
    sub_choice: Optional[tuple] = None                # ("srt", path) ou ("mkv", idx)
    orig_audio_lang: Optional[str] = None             # libellé de la piste originale dans la sortie
    db_reduct: float = -5.0                           # ducking en dB
    offset_ms: int = 0                                # décalage ST/TTS
    bg_mix: float = 1.0                               # gain BG
    tts_mix: float = 1.0                              # gain TTS
    audio_codec: str = "ac3"                          # Codec de des pistes audio
    audio_bitrate: int = 320                          # Bitrate des pistes audio
    voice_id: Optional[str] = None                    # identifiant de voix
    audio_codec_args: Iterable[str] = ()              # args ffmpeg audio final (ex: "-c:a","aac","-b:a","192k")
    sub_codec: str = "srt"                            # "srt" ou "ass"


@dataclass
class Services:
    resolve_srt_for_video: Callable[[str, tuple], Optional[str]]
    generate_dub_audio: Callable[..., str]
    choose_audio_track: Callable[[str], int]
    choose_subtitle_source: Callable[[str], Optional[tuple]]


def _video_ext_from_codec_args(args: Iterable[str]) -> str:
    codec = None
    a = list(args) if args is not None else []
    for i, tok in enumerate(a):
        if tok == "-c:a" and i + 1 < len(a):
            codec = a[i + 1].lower()
            break
    return ".mkv"


def _audio_ext_from_codec_args(args: Iterable[str]) -> str:
    codec = None
    a = list(args) if args is not None else []
    for i, tok in enumerate(a):
        if tok == "-c:a" and i + 1 < len(a):
            codec = a[i + 1].lower()
            break
    if codec in ("aac",):
        return ".m4a"
    if codec in ("libmp3lame", "mp3"):
        return ".mp3"
    if codec in ("ac3",):
        return ".ac3"
    if codec in ("flac",):
        return ".flac"
    if codec in ("libopus", "opus"):
        return ".opus"
    if codec in ("libvorbis", "vorbis"):
        return ".ogg"
    if codec in ("pcm_s16le",):
        return ".wav"
    return ".mka"


def process_one_video(
    video_name: str,
    opts: DubOptions,
    svcs: Services,
    *,
    limit_duration_sec: Optional[int] = None,
    test_prefix: str = "",
) -> Optional[str]:
    """
    Traite UNE vidéo avec les options et services fournis.
    Retourne le chemin de la vidéo finale, ou None si annulé.
    """
    video_full = join_input(video_name)
    base, ext = os.path.splitext(os.path.basename(video_full))

    # 1) Piste audio source
    audio_idx = opts.audio_ffmpeg_index
    if audio_idx is None:
        audio_idx = svcs.choose_audio_track(video_full)

    # 2) Source des sous-titres
    sub_choice = opts.sub_choice
    if sub_choice is None:
        sub_choice = svcs.choose_subtitle_source(video_full)
        if sub_choice is None:
            return None

    # 3) Résolution vers un SRT exploitable
    srt_path = svcs.resolve_srt_for_video(video_full, sub_choice)
    if not srt_path:
        _step(f"Impossible d'obtenir un SRT pour {video_name}.")
        return None

    # 4) Nettoyage SRT
    strip_subtitle_tags_inplace(srt_path)

    # 5) Libellé de la piste d'origine
    orig_audio_lang = opts.orig_audio_lang
    if not orig_audio_lang:
        orig_audio_lang = svcs.ask_str("Nom de la piste d'origine (ex. Japonais)", "Original")

    # 6) Extraction audio d'origine (WAV PCM)
    orig_wav = join_output(f"{test_prefix}{base}_orig.wav")
    _step("Extraction de l'audio d'origine (WAV PCM)...")
    _md(
        extract_audio_track, 
        video_full, 
        audio_idx, 
        orig_wav, 
        duration_sec=limit_duration_sec
    )
    
    # Durée cible (utile pour calages éventuels)
    try:
        orig_len_ms = len(AudioSegment.from_file(orig_wav))
    except Exception:
        orig_len_ms = None

    # 7) Parsing SRT (sert aussi au ducking)
    subtitles = parse_srt_file(srt_path, duration_limit_sec=limit_duration_sec)
    if not subtitles:
        print("Aucun sous-titre exploitable.")
        return None

    # 8) Génération TTS alignée (WAV)
    tts_wav = join_output(f"{test_prefix}{base}_tts.wav")
    _step("Génération TTS (WAV)...")
    _md(
        svcs.generate_dub_audio,
        srt_file=srt_path,
        output_wav=tts_wav,
        voice_id=opts.voice_id,
        duration_limit_sec=limit_duration_sec,
        target_total_duration_ms=orig_len_ms,
        offset_ms=opts.offset_ms,
    )

    # 9) Ducking de l'audio d'origine pendant les dialogues
    ducked_wav = join_output(f"{test_prefix}{base}_ducked.wav")
    _step("Ducking de l'audio original pendant les dialogues...")
    _md(
        lower_audio_during_subtitles,
        audio_file=orig_wav,
        subtitles=subtitles,
        output_wav=ducked_wav,
        reduction_db=opts.db_reduct,
        offset_ms=opts.offset_ms,
    )

    # 10) Mix final BG + TTS
    mixed_audio = join_output(f"{test_prefix}{base}_mix{_audio_ext_from_codec_args(opts.audio_codec_args)}")
    _step("Mixage final BG/TTS...")
    _md(
        mix_audios, 
        ducked_wav,
        tts_wav,
        mixed_audio,
        bg_mix=opts.bg_mix,
        tts_mix=opts.tts_mix,
        audio_codec_args=list(opts.audio_codec_args),
    )

    # 11) Encodage de la piste originale dans le codec final
    orig_encoded = join_output(f"{test_prefix}{base}_orig_enc{_audio_ext_from_codec_args(opts.audio_codec_args)}")
    _step("Encodage de l'audio d'origine dans le codec final...")
    _md(
        encode_original_audio_to_final_codec, 
        orig_wav,
        orig_encoded,
        audio_codec_args=list(opts.audio_codec_args),
    )

    # 12) Clip vidéo si TEST
    video_for_merge = video_full
    tmp_clip = None
    if limit_duration_sec is not None:
        tmp_clip = join_output(f"{test_prefix}{base}_clip{ext}")
        subprocess.run([
            "ffmpeg", "-y",
            "-hide_banner", "-loglevel", "error", "-stats",
            "-i", video_full,
            "-t", str(int(limit_duration_sec)),
            "-c", "copy",
            tmp_clip
        ], check=True)
        video_for_merge = tmp_clip

    # 13) Fusion finale (vidéo + 2 audios + ST)
    final_ext = _video_ext_from_codec_args(opts.audio_codec_args)
    dub_code = _dub_code_from_voice(getattr(opts, 'voice_id', None))
    final_video = join_output(f"{test_prefix}{base} [dub-{dub_code}]{final_ext}")
    _step("Fusion finale (conteneur)...")
    _md(
        merge_to_container,
        video_for_merge,
        mixed_audio,
        orig_encoded,
        srt_path,
        final_video,
        orig_audio_name_for_title=orig_audio_lang,
        sub_codec=opts.sub_codec,
        offset_ms=opts.offset_ms,
    )

    # 14) Nettoyage
    for f in (
        orig_wav, 
        tts_wav, 
        ducked_wav, 
        mixed_audio, 
        orig_encoded
    ):
        try:
            if f and os.path.exists(f):
                os.remove(f)
        except Exception:
            pass
    if tmp_clip and os.path.exists(tmp_clip):
        try:
            os.remove(tmp_clip)
        except Exception:
            pass
    # time.sleep(20)
    return final_video
