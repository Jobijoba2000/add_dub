# src/add_dub/core/pipeline.py
import os
import subprocess
from typing import Callable, Optional
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


def _audio_ext_from_codec_args(audio_codec_args) -> str:
    """
    Déduit l'extension audio finale depuis les args codec ffmpeg passés.
    """
    args = list(audio_codec_args) if audio_codec_args else []
    codec = None
    for i, tok in enumerate(args):
        if tok == "-c:a" and i + 1 < len(args):
            codec = args[i + 1].lower()
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
    return ".m4a"


def _video_ext_from_codec_args(audio_codec_args) -> str:
    """
    Règle de conteneur : .mp4 si AAC, sinon .mkv.
    """
    args = list(audio_codec_args) if audio_codec_args else []
    codec = None
    for i, tok in enumerate(args):
        if tok == "-c:a" and i + 1 < len(args):
            codec = args[i + 1].lower()
            break
    return ".mp4" if codec == "aac" else ".mkv"


def process_one_video(
    video_name: str,
    voice_id: str,
    *,
    audio_ffmpeg_index: Optional[int] = None,
    sub_choice: Optional[tuple] = None,          # ("srt", path) ou ("mkv", idx)
    orig_audio_name: Optional[str] = None,
    limit_duration_sec: Optional[int] = None,
    test_prefix: str = "",
    # config passée par __main__ (ex-”globals”)
    db_reduct: float = -5.0,
    offset_ms: int = 0,
    bg_mix: float = 1.0,
    tts_mix: float = 1.0,
    audio_codec_args: tuple | list = (),
    sub_codec: str = "srt",
    # callbacks fournis par __main__ (pour éviter import inverse)
    choose_audio_track_fn: Optional[Callable[[str], int]] = None,
    choose_subtitle_source_fn: Optional[Callable[[str], Optional[tuple]]] = None,
    ask_str_fn: Optional[Callable[[str, str], str]] = None,
    resolve_srt_for_video_fn: Optional[Callable[[str, tuple], Optional[str]]] = None,
    generate_dub_audio_fn: Optional[Callable[..., str]] = None,
) -> Optional[str]:
    """
    Traite une vidéo située dans input/ et produit la sortie dans output/.
    Retourne le chemin du fichier final ou None.
    """
    video_fullpath = join_input(video_name)
    base, _ext = os.path.splitext(video_name)

    # 1) Choix de la piste audio (ffmpeg index)
    if audio_ffmpeg_index is None:
        if not choose_audio_track_fn:
            raise RuntimeError("choose_audio_track_fn manquant")
        audio_ffmpeg_index = choose_audio_track_fn(video_fullpath)

    # 2) Résolution du SRT à utiliser
    if not resolve_srt_for_video_fn:
        raise RuntimeError("resolve_srt_for_video_fn manquant")

    if sub_choice is None:
        if not choose_subtitle_source_fn:
            raise RuntimeError("choose_subtitle_source_fn manquant")
        chosen = choose_subtitle_source_fn(video_fullpath)
        if chosen is None:
            print(f"Aucun sous-titre pour {video_name}.")
            return None
        srt_path = resolve_srt_for_video_fn(video_fullpath, chosen)
    else:
        srt_path = resolve_srt_for_video_fn(video_fullpath, sub_choice)

    if not srt_path:
        print(f"Impossible d'obtenir un SRT pour {video_name}.")
        return None

    # 3) Nettoyage SRT (balises/ass)
    strip_subtitle_tags_inplace(srt_path)

    # 4) Nom de la piste originale
    if orig_audio_name is None:
        if not ask_str_fn:
            raise RuntimeError("ask_str_fn manquant")
        orig_audio_name = ask_str_fn("\nNom de la piste audio d'origine (ex. Japonais)", "Original")

    # 5) Extraction audio d'origine (WAV PCM)
    orig_wav = join_output(f"{test_prefix}{base}_orig.wav")
    print("\nExtraction de l'audio d'origine (WAV PCM)...")
    extract_audio_track(video_fullpath, audio_ffmpeg_index, orig_wav, duration_sec=limit_duration_sec)

    # Durée cible pour le TTS (évite de couper la fin)
    orig_len_ms = len(AudioSegment.from_file(orig_wav))

    # 6) Parsing SRT
    subtitles = parse_srt_file(srt_path, duration_limit_sec=limit_duration_sec)

    # 7) Ducking du BG sur les passages ST
    lowered_wav = join_output(f"{test_prefix}{base}_lowered.wav")
    print("\nDucking des passages sous-titrés -> WAV...")
    lower_audio_during_subtitles(
        orig_wav,
        subtitles,
        lowered_wav,
        reduction_db=db_reduct,
        fade_duration=100,
        offset_ms=offset_ms,
    )

    # 8) Génération TTS (WAV)
    if not generate_dub_audio_fn:
        raise RuntimeError("generate_dub_audio_fn manquant")
    dub_wav = join_output(f"{test_prefix}{base}_dub.wav")
    print("\nGénération TTS -> WAV...")
    generate_dub_audio_fn(
        srt_path,
        dub_wav,
        voice_id,
        duration_limit_sec=limit_duration_sec,
        target_total_duration_ms=orig_len_ms,
        offset_ms=offset_ms,  # <-- ajoute cette ligne
    )


    # 9) Mix BG+TTS vers codec final
    mixed_ext = _audio_ext_from_codec_args(audio_codec_args)
    mixed_audio = join_output(f"{test_prefix}{base}_mixed{mixed_ext}")
    print("\nMixage BG+TTS...")
    mix_audios(lowered_wav, dub_wav, mixed_audio, bg_mix, tts_mix, audio_codec_args)

    # 10) Réencodage de l'original vers le même codec (piste #2)
    orig_encoded = join_output(f"{test_prefix}{base}_orig{mixed_ext}")
    print("\nRéencodage de la piste originale au codec final...")
    encode_original_audio_to_final_codec(orig_wav, orig_encoded, audio_codec_args)

    # 11) Fusion finale (vidéo + 2 audios + ST non par défaut)
    final_ext = _video_ext_from_codec_args(audio_codec_args)

    # — Couper la vidéo si on est en mode TEST (limit_duration_sec)
    video_for_merge = video_fullpath
    tmp_clip = None
    if limit_duration_sec is not None:
        clip_ext = os.path.splitext(video_fullpath)[1]
        tmp_clip = join_output(f"{test_prefix}{base}_clip{clip_ext}")
        subprocess.run([
            "ffmpeg", "-y",
            "-hide_banner", "-loglevel", "error", "-stats",
            "-i", video_fullpath,
            "-t", str(int(limit_duration_sec)),
            "-c", "copy",
            tmp_clip
        ], check=True)
        video_for_merge = tmp_clip

    final_video = join_output(f"{test_prefix}dub_{base}{final_ext}")
    print("\nFusion finale (vidéo + 2 audios + ST non par défaut)...")
    merge_to_container(
        video_for_merge,
        mixed_audio,
        orig_encoded,
        srt_path,
        final_video,
        orig_audio_name_for_title=orig_audio_name,
        sub_codec=sub_codec,
    )

    print(f"\nFichier final : {final_video}")

    # 12) Nettoyage des intermédiaires
    for f in (orig_wav, lowered_wav, dub_wav, mixed_audio, orig_encoded):
        try:
            if os.path.exists(f):
                os.remove(f)
        except Exception as e:
            print(f"Suppression échouée ({f}): {e}")

    # Clip vidéo temporaire du mode test
    if tmp_clip and os.path.exists(tmp_clip):
        try:
            os.remove(tmp_clip)
        except Exception as e:
            print(f"Suppression échouée ({tmp_clip}): {e}")

    return final_video
