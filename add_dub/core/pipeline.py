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
    dub_in_one_pass,
)
import re
from add_dub.core.options import DubOptions
from add_dub.core.services import Services
from pprint import pprint
from add_dub.logger import (log_call, log_time)

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

@log_time
@log_call
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

    print(video_name)

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
    extract_audio_track(
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
    svcs.generate_dub_audio(
        srt_file=srt_path,
        output_wav=tts_wav,
        opts=opts,
        duration_limit_sec=limit_duration_sec,
        target_total_duration_ms=orig_len_ms,
    )

    # 9) Ducking de l'audio d'origine pendant les dialogues
    ducked_wav = join_output(f"{test_prefix}{base}_ducked.wav")
    _step("Ducking de l'audio original pendant les dialogues...")
    lower_audio_during_subtitles(
        audio_file=orig_wav,
        subtitles=subtitles,
        output_wav=ducked_wav,
        reduction_db=opts.db_reduct,
        offset_ms=opts.offset_ms,
    )

    # 10) Clip vidéo si TEST
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

    # 11) Sortie finale (vidéo + 2 audios + ST) — en une seule passe
    # final_ext = _video_ext_from_codec_args(opts.audio_codec_args)
    # dub_code = _dub_code_from_voice(getattr(opts, 'voice_id', None))
    # final_video = join_output(f"{test_prefix}{base} [dub-{dub_code}]{final_ext}")
    # _step("Mixage/Encodage/Mux en une passe...")
    # dub_in_one_pass(
        # video_fullpath=video_for_merge,
        # bg_wav=ducked_wav,
        # tts_wav=tts_wav,
        # original_wav=orig_wav,
        # subtitle_srt_path=srt_path,
        # output_video_path=final_video,
        # bg_mix=opts.bg_mix,
        # tts_mix=opts.tts_mix,
        # audio_codec_args=list(opts.audio_codec_args),
        # opts=opts,
    # )
    
    
    
    
    # 11) Sortie finale
    final_ext = _video_ext_from_codec_args(opts.audio_codec_args)
    dub_code = _dub_code_from_voice(getattr(opts, 'voice_id', None))
    final_video = join_output(f"{test_prefix}{base} [dub-{dub_code}]{final_ext}")

    _step("Mixage/Encodage/Mux final...")
    if getattr(opts, "use_merge_offsets", False):
        print("ok")
        from add_dub.adapters.ffmpeg import merge_with_offsets_and_mix
        merge_with_offsets_and_mix(
            video_fullpath=video_for_merge,
            ducked_wav=ducked_wav,
            tts_wav=tts_wav,
            subtitle_srt_path=srt_path,
            output_video_path=final_video,
            orig_audio_name_for_title=orig_audio_lang,
            sub_codec=opts.sub_codec,
            bg_mix=opts.bg_mix,
            tts_mix=opts.tts_mix,
            offset_audio_ms=0,
            offset_video_ms=opts.offset_video_ms,
            offset_subtitle_ms=opts.offset_ms,
            set_dub_default=True,
            add_subtitle=True,
            audio_codec=opts.audio_codec,
            audio_bitrate=opts.audio_bitrate
        )
    else:
   

        dub_in_one_pass(
            video_fullpath=video_for_merge,
            bg_wav=ducked_wav,
            tts_wav=tts_wav,
            original_wav=orig_wav,
            subtitle_srt_path=srt_path,
            output_video_path=final_video,
            bg_mix=opts.bg_mix,
            tts_mix=opts.tts_mix,
            audio_codec_args=list(opts.audio_codec_args),
            opts=opts,
        )


    
    
    
    
    
    
    # 12) Nettoyage
    for f in (
        orig_wav,
        tts_wav,
        ducked_wav,
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

    return final_video
