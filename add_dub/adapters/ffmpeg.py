# add_dub/adapters/ffmpeg.py
import os
import json
import time
import subprocess
import add_dub.helpers.number as _n
import sys
from pathlib import Path
from add_dub.core.options import DubOptions
from add_dub.logger import (log_call, log_time)
from add_dub.i18n import t


def run_ffmpeg_with_percentage(cmd, duration_source):
    """
    cmd : liste FFmpeg déjà contenant -nostats -progress pipe:1
    duration_source : fichier dont on prend la durée (ex: la vidéo d'entrée)
    """
    duration = float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", duration_source],
        text=True, encoding="utf-8", errors="replace"
    ).strip())

    p = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,          # flux -progress
        stderr=subprocess.DEVNULL,
        text=True, encoding="utf-8", errors="replace",
        bufsize=1
    )

    try:
        for line in p.stdout:
            if line.startswith("out_time_ms="):
                micro_s = float(line.split("=", 1)[1])
                pct = (micro_s / (duration * 10000.0))
                print(f"\r{pct:.0f}%", end="", flush=True)
            elif line.strip() == "progress=end":
                print("\r100%")
                break
    finally:
        rc = p.wait()
        if rc != 0:
            raise subprocess.CalledProcessError(rc, cmd)

@log_time
@log_call()
def get_track_info(video_fullpath):
    """
    Retourne la liste des streams 'audio' (objets JSON ffprobe).
    """
    cmd = [
        "ffprobe", "-v", "error",
        "-print_format", "json",
        "-show_streams",
        video_fullpath,
    ]
    result = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace"
    )
    data = json.loads(result.stdout) if result.stdout else {}
    audio_tracks = []
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "audio":
            audio_tracks.append(stream)
    return audio_tracks

@log_time
@log_call()
def extract_audio_track(video_fullpath, audio_track_index, output_wav, duration_sec=None):
    """
    Extrait la piste audio ffmpeg index 'audio_track_index' en WAV PCM 16-bit.
    """
    cmd = [
        "ffmpeg", "-y",
        "-hide_banner", "-loglevel", "error", 
        "-nostats", "-progress", "pipe:1",
        "-i", video_fullpath,
        "-map", f"0:{audio_track_index}",
        "-vn",
        "-c:a", "pcm_s16le",
    ]
    if duration_sec is not None:
        cmd.extend(["-t", str(int(duration_sec))])
    cmd.append(output_wav)

    # subprocess.run(cmd, check=True)
    run_ffmpeg_with_percentage(cmd, duration_source=video_fullpath)
    return output_wav


@log_time
@log_call(exclude="subtitle_srt_path")
def dub_in_one_pass(
    *,
    video_fullpath: str,
    bg_wav: str,                 # audio1_wav (BG)
    tts_wav: str,                # audio2_wav (TTS)
    original_wav: str,           # WAV de l'audio d'origine (déjà extrait)
    subtitle_srt_path: str,
    output_video_path: str,
    opts: DubOptions,
):
    """
    Fait en UNE PASSE :
      - mix BG+TTS (amix) avec volumes,
      - encode le mix au codec cible (audio_codec_args),
      - encode l'audio original au même codec,
      - applique les offsets (vidéo et sous-titres),
      - mux dans le conteneur final avec métadonnées/dispositions.

    Entrées:
      0: (avec -itsoffset) vidéo source
      1: bg_wav
      2: tts_wav
      3: original_wav (sera encodé comme piste audio #1)
      4: (avec -itsoffset) sous-titres SRT
    Sorties mappées:
      - 0:v:0  (copié ou transcodé selon extension)
    """
    # Calcul des offsets en secondes
    offset_s = (opts.offset_ms or 0) / 1000.0
    offset_video_s = (opts.offset_video_ms or 0) / 1000.0

    # Titrages
    lang_orig = opts.orig_audio_lang or "Original"
    lang_dest = opts.translate_to or "Dubbed"
    dub_title = f"{lang_orig} -> {lang_dest}"
    orig_title = lang_orig
    sub_title = lang_dest

    # Choix de copie/transcodage vidéo selon extension
    extension_source = Path(video_fullpath).suffix.lower()
    if extension_source == ".avi":
        copy_video = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18"]
    else:
        copy_video = ["-c:v", "copy"]

    # Mix en s16/stereo et resample asynchrone, volumes appliqués
    filter_str = (
        f"[1:a]aformat=sample_fmts=s16:channel_layouts=stereo,aresample=async=1,volume={opts.bg_mix}[bg];"
        f"[2:a]aformat=sample_fmts=s16:channel_layouts=stereo,aresample=async=1,volume={opts.tts_mix}[tts];"
        f"[bg][tts]amix=inputs=2:duration=longest:dropout_transition=0[a_mix]"
    )

    # Construction commande unique
    cmd = [
        "ffmpeg", "-y",
        "-hide_banner", "-loglevel", "error",
        "-nostats", "-progress", "pipe:1",

        # 0: vidéo (avec offset vidéo)
        "-itsoffset", str(offset_video_s), "-i", video_fullpath,

        # 1: BG wav, 2: TTS wav, 3: original wav
        "-i", bg_wav,
        "-i", tts_wav,
        "-i", original_wav,

        # 4: sous-titres (avec offset ST)
        "-itsoffset", str(offset_s), "-i", subtitle_srt_path,

        # Filter pour fabriquer [a_mix]
        "-filter_complex", filter_str,

        # Mapping sorties
        "-map", "0:v:0",
        "-map", "[a_mix]",   # audio 0 (dub)
        "-map", "3:a:0",     # audio 1 (original)
        "-map", "4:0",       # sous-titres

    ] + copy_video + [
        # Audio: même codec/paramètres pour TOUTES les pistes audio
        # (audio_codec_args est appliqué globalement à -c:a)
        "-c:a", opts.audio_codec, "-b:a", f"{int(opts.audio_bitrate)}k", 
        # Force stéréo pour la piste audio 1 (original encodé), la 0 sort déjà en stéréo du mix
        "-ac:a:1", "2",

        # Codec des sous-titres
        "-c:s:0", opts.sub_codec,

        # Dispositions
        "-disposition:a:0", "default",
        "-disposition:a:1", "0",
        "-disposition:s:0", "0",

        # Métadonnées
        "-metadata:s:a:0", f"title={dub_title}",
        "-metadata:s:a:1", f"title={orig_title}",
        "-metadata:s:s:0", f"title={sub_title}",

        # Sortie finale
        output_video_path,
    ]

    # Barre de progression (basée sur la durée vidéo)
    run_ffmpeg_with_percentage(cmd, duration_source=video_fullpath)
    return output_video_path
