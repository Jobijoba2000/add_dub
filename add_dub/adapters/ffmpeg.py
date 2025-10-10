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


def run_ffmpeg_with_percentage(cmd, duration_source):
    """
    cmd : liste FFmpeg déjà contenant -nostats -progress pipe:1
    duration_source : fichier dont on prend la durée (ex: la vidéo d'entrée)
    """
    duration = float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", duration_source],
        text=True
    ).strip())

    p = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,          # flux -progress
        stderr=subprocess.DEVNULL,
        text=True,
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
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
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
@log_call()
def mix_audios(audio1_wav, audio2_wav, output_file, bg_mix, tts_mix, audio_codec_args):
    """
    Mixe audio1 (BG) + audio2 (TTS) -> fichier audio final (codec défini par audio_codec_args).
    Utilise la durée la plus longue pour éviter de couper la fin.
    """
    if os.path.getsize(audio1_wav) == 0 or os.path.getsize(audio2_wav) == 0:
        print("Un des fichiers audio est vide. Impossible de mixer.")
        return

    filter_str = (
        f"[0:a]aformat=sample_fmts=s16:channel_layouts=stereo,aresample=async=1,volume={bg_mix}[first];"
        f"[1:a]aformat=sample_fmts=s16:channel_layouts=stereo,aresample=async=1,volume={tts_mix}[second];"
        "[first][second]amix=inputs=2:duration=longest:dropout_transition=0[aout]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-hide_banner", "-loglevel", "error", 
        "-nostats", "-progress", "pipe:1",
        "-i", audio1_wav,
        "-i", audio2_wav,
        "-filter_complex", filter_str,
        "-map", "[aout]",
    ] + list(audio_codec_args) + [
        output_file
    ]

    # subprocess.run(cmd, check=True)
    run_ffmpeg_with_percentage(cmd, duration_source=audio1_wav)
    return output_file

@log_time
@log_call()
def encode_original_audio_to_final_codec(original_wav, output_audio, audio_codec_args):
    """
    Réencode l'audio d'origine (WAV) vers le codec final (args fournis),
    pour l'ajouter comme deuxième piste audio.
    """
    cmd = [
        "ffmpeg", "-y",
        "-hide_banner", "-loglevel", "error",
        "-nostats", "-progress", "pipe:1",
        "-i", original_wav,
        "-ac", "2",
    ] + list(audio_codec_args) + [
        output_audio
    ]

    # subprocess.run(cmd, check=True)
    run_ffmpeg_with_percentage(cmd, duration_source=original_wav)
    return output_audio

@log_time
@log_call(exclude="subtitle_srt_path")
def merge_to_container(
    video_fullpath,
    mixed_audio_file,
    orig_audio_encoded_file,
    subtitle_srt_path,
    output_video_path,
    opts: DubOptions,
):
    """
    Fusionne :
      - Vidéo originale (copiée)
      - Piste audio 0 : mix TTS (par défaut)  -> title: "<orig> doublé en Français"
      - Piste audio 1 : audio original (même codec) -> title: "<orig>"
      - Piste sous-titres : présente mais non par défaut -> title: "Français"
    Pas de -shortest pour garder toute la durée.
    """

    offset_s = _n.int_to_scaled_str(opts.offset_ms)
    offset_video_s = _n.int_to_scaled_str(opts. offset_video_ms)
    
    inputs = [         
        "-itsoffset", offset_video_s,
        "-i", video_fullpath,   
        "-i", mixed_audio_file,                  
        "-i", orig_audio_encoded_file,
        "-itsoffset", offset_s,
        "-i", subtitle_srt_path,         
    ]

    dub_title = f"{opts.orig_audio_lang} doublé en Français"
    orig_title = opts.orig_audio_lang
    sub_title = "Français"
    
    extension_source = Path(video_fullpath).suffix.lower()
    if extension_source == ".avi":
        copy_video = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "copy"]
    else:
        copy_video = ["-c", "copy"]
    
    cmd = [
        "ffmpeg", "-y",
        "-hide_banner", "-loglevel", "error", 
        "-nostats", "-progress", "pipe:1",
    ] + inputs + [
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-map", "2:a:0",
        "-map", "3:0",
    ] + copy_video + [
        "-c:a:0", "copy",
        "-c:a:1", "copy",
        "-c:s:0", opts.sub_codec,
        "-disposition:a:0", "default",
        "-disposition:a:1", "0",
        "-disposition:s:0", "0",
        "-metadata:s:a:0", f"title={dub_title}",
        "-metadata:s:a:1", f"title={orig_title}",
        "-metadata:s:s:0", f"title={sub_title}",
        output_video_path,
    ]
    # subprocess.run(cmd, check=True)
    run_ffmpeg_with_percentage(cmd, duration_source=video_fullpath)
    return output_video_path


def merge_to_container_test(
    video_fullpath,
    mixed_audio_file,
    subtitle_srt_path,
    output_video_path,
    orig_audio_name_for_title,
    sub_codec,                 # ex: "srt" (recommandé en MKV), ou "ass" si tu fournis un .ass
    offset_ms,
    set_dub_default=True,      # True → la nouvelle piste audio sera par défaut
    add_subtitle=True          # True → on ajoute la piste de sous-titres externe
):
    """
    Remux MKV :
      - Conserve la vidéo et toutes les pistes du fichier source (vidéo, audios, sous-titres).
      - Ajoute la piste audio mixée en dernier, avec title "<orig> doublé en Français".
      - Option : met la piste audio ajoutée par défaut (et retire 'default' des autres).
      - Option : ajoute un SRT externe, avec offset (uniquement sur le SRT), nommé "Français".
    """

    dub_title = f"{orig_audio_name_for_title} doublé en Français"

    has_offset = bool(offset_ms) and offset_ms != 0
    offset_s = f"{offset_ms/1000:.3f}" if has_offset else None

    def count_streams(path: str, kind: str) -> int:
        r = subprocess.run(
            ["ffprobe", "-v", "error",
             "-select_streams", kind,
             "-show_entries", "stream=index",
             "-of", "csv=p=0",
             path],
            capture_output=True, text=True
        )
        return sum(1 for line in r.stdout.splitlines() if line.strip())

    # Indices de sortie calculés (après mapping)
    orig_audio_count = count_streams(video_fullpath, "a")
    new_audio_out_index = orig_audio_count  # la nouvelle audio arrivera en dernier

    orig_sub_count = count_streams(video_fullpath, "s")
    new_sub_out_index = orig_sub_count      # le sous-titre externe sera le suivant

    # --- Entrées ---
    inputs = []
    # 0) Source (pas d'offset)
    inputs += ["-i", video_fullpath]
    # 1) Audio mixée (PAS d'offset ici, déjà appliqué en amont)
    inputs += ["-i", mixed_audio_file]
    # 2) SRT externe (offset appliqué ICI uniquement sur le SRT)
    if add_subtitle:
        if has_offset:
            inputs += ["-itsoffset", offset_s]
        # On force le demuxer SRT pour éviter l'ambiguïté
        inputs += ["-f", "srt", "-i", subtitle_srt_path]

    # --- Commande FFmpeg ---
    cmd = [
        "ffmpeg", "-y",
        "-hide_banner", "-loglevel", "error",
        "-nostats", "-progress", "pipe:1",
    ] + inputs + [
        # Vidéo : première piste vidéo de la source (mets "0:v" si tu veux toutes)
        "-map", "0:v:0",
        # Audios : toutes les pistes audio de la source
        "-map", "0:a",
        # Nouvelle audio : la piste du fichier 1 (ajoutée en dernier)
        "-map", "1:a:0",
        # Sous-titres d'origine (s'ils existent)
        "-map", "0:s?",
    ]

    # Sous-titre externe optionnel (avec offset déjà appliqué à l'entrée)
    if add_subtitle:
        cmd += ["-map", "2:s:0"]

    # Copie par défaut
    cmd += ["-c", "copy"]

    # Title de la nouvelle audio (index de sortie calculé)
    cmd += ["-metadata:s:a:{}".format(new_audio_out_index), f"title={dub_title}"]

    # Sous-titre externe : title + RÉENCODAGE de cette piste (pour graver l'offset)
    if add_subtitle:
        cmd += ["-metadata:s:s:{}".format(new_sub_out_index), "title=Français"]
        # Réencode UNIQUEMENT le sous-titre ajouté ; tout le reste reste en copy
        cmd += ["-c:s:{}".format(new_sub_out_index), sub_codec]

    # Piste audio par défaut (optionnel)
    if set_dub_default:
        # Retire 'default' de toutes les pistes audio existantes
        cmd += ["-disposition:a", "0"]
        # Met 'default' sur la nouvelle (indice calculé)
        cmd += ["-disposition:a:{}".format(new_audio_out_index), "default"]
        cmd += ["-disposition:s", "0"]

    # Sortie MKV
    cmd += [output_video_path]

    # Exécution
    subprocess.run(cmd, check=True)
    # run_ffmpeg_with_percentage(cmd, duration_source=video_fullpath)






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
    bg_mix: float,
    tts_mix: float,
    audio_codec_args: list[str], # ex: ["-c:a","aac","-b:a","192k"]
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
      - [a_mix] (piste audio #0, mix BG+TTS, encodée)
      - 3:a:0   (piste audio #1, original, encodé)
      - 4:0     (piste sous-titres)
    """

    # Sanity rapide sur les entrées audio
    if os.path.getsize(bg_wav) == 0 or os.path.getsize(tts_wav) == 0:
        print("Un des fichiers (BG/TTS) est vide. Impossible de mixer.")
        return

    # Offsets
    offset_s = _n.int_to_scaled_str(opts.offset_ms)
    offset_video_s = _n.int_to_scaled_str(opts.offset_video_ms)

    # Titrages
    dub_title = f"{opts.orig_audio_lang} doublé en Français"
    orig_title = opts.orig_audio_lang
    sub_title = "Français"

    # Choix de copie/transcodage vidéo selon extension
    extension_source = Path(video_fullpath).suffix.lower()
    if extension_source == ".avi":
        copy_video = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18"]
    else:
        copy_video = ["-c:v", "copy"]

    # Mix en s16/stereo et resample asynchrone, volumes appliqués
    filter_str = (
        f"[1:a]aformat=sample_fmts=s16:channel_layouts=stereo,aresample=async=1,volume={bg_mix}[bg];"
        f"[2:a]aformat=sample_fmts=s16:channel_layouts=stereo,aresample=async=1,volume={tts_mix}[tts];"
        f"[bg][tts]amix=inputs=2:duration=longest:dropout_transition=0[a_mix]"
    )

    # Construction commande unique
    cmd = [
        "ffmpeg", "-y",
        "-hide_banner", "-loglevel", "error",
        "-nostats", "-progress", "pipe:1",

        # 0: vidéo (avec offset vidéo)
        "-itsoffset", offset_video_s, "-i", video_fullpath,

        # 1: BG wav, 2: TTS wav, 3: original wav
        "-i", bg_wav,
        "-i", tts_wav,
        "-i", original_wav,

        # 4: sous-titres (avec offset ST)
        "-itsoffset", offset_s, "-i", subtitle_srt_path,

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
    ] + list(audio_codec_args) + [
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



@log_time
def merge_with_offsets_and_mix(
    video_fullpath: str,
    ducked_wav: str,
    tts_wav: str,
    subtitle_srt_path: str | None,
    output_video_path: str,
    orig_audio_name_for_title: str,
    sub_codec: str,
    bg_mix: float,
    tts_mix: float,
    offset_audio_ms: int = 0,
    offset_video_ms: int = 0,
    offset_subtitle_ms: int = 0,
    set_dub_default: bool = True,
    add_subtitle: bool = True,
    audio_codec: str | None = None,
    audio_bitrate: int | None = None
):
    def ms_to_sec(ms: int) -> str:
        return f"{ms / 1000:.3f}"

    dub_title = f"{orig_audio_name_for_title} doublé en Français"

    def count_streams(path: str, kind: str) -> int:
        r = subprocess.run(
            ["ffprobe", "-v", "error",
             "-select_streams", kind,
             "-show_entries", "stream=index",
             "-of", "csv=p=0", path],
            capture_output=True, text=True
        )
        return sum(1 for line in r.stdout.splitlines() if line.strip())

    # --- Compte les pistes existantes ---
    orig_audio_count = count_streams(video_fullpath, "a")
    new_audio_out_index = orig_audio_count
    orig_sub_count = count_streams(video_fullpath, "s")
    new_sub_out_index = orig_sub_count

    # --- Inputs ---
    inputs = []
    if offset_video_ms != 0:
        inputs += ["-itsoffset", ms_to_sec(offset_video_ms)]
    inputs += ["-i", video_fullpath]
    
    if offset_audio_ms != 0:
        inputs += ["-itsoffset", ms_to_sec(offset_audio_ms)]
    inputs += ["-i", ducked_wav]

    if offset_audio_ms != 0:
        inputs += ["-itsoffset", ms_to_sec(offset_audio_ms)]
    inputs += ["-i", tts_wav]

    if add_subtitle and subtitle_srt_path:
        if offset_subtitle_ms != 0:
            inputs += ["-itsoffset", ms_to_sec(offset_subtitle_ms)]
        inputs += ["-f", "srt", "-i", subtitle_srt_path]

    # --- Filtre audio ---
    filter_str = (
        f"[1:a]aformat=sample_fmts=s16:channel_layouts=stereo,aresample=async=1,volume={bg_mix}[bg];"
        f"[2:a]aformat=sample_fmts=s16:channel_layouts=stereo,aresample=async=1,volume={tts_mix}[tts];"
        f"[bg][tts]amix=inputs=2:duration=longest:dropout_transition=0[a_mix]"
    )

    # --- Commande de base ---
    cmd = [
        "ffmpeg", "-y",
        "-hide_banner", "-loglevel", "error",
        "-nostats", "-progress", "pipe:1",
    ] + inputs + [
        "-filter_complex", filter_str,
        "-map", "0:v:0",
        "-map", "0:a",
        "-map", "[a_mix]",
        "-map", "0:s?",
    ]

    # --- Mapping SRT externe si présent ---
    if add_subtitle and subtitle_srt_path:
        srt_input_index = inputs.count("-i") - 1
        cmd += ["-map", f"{srt_input_index}:s:0"]

    # --- Codecs ---
    cmd += ["-c:v", "copy"]     # copie vidéo
    cmd += ["-c:a", "copy"]     # copie pistes audio originales
    cmd += ["-c:s", "copy"]     # copie sous-titres originaux

    # encode uniquement la piste audio mixée
    if audio_codec and audio_bitrate:
        cmd += [
            f"-c:a:{new_audio_out_index}", audio_codec,
            f"-b:a:{new_audio_out_index}", f"{audio_bitrate}k"
        ]
    else:
        cmd += [
            f"-c:a:{new_audio_out_index}", "aac",
            f"-b:a:{new_audio_out_index}", "192k"
        ]

    # --- Métadonnées piste audio mixée ---
    cmd += ["-metadata:s:a:{}".format(new_audio_out_index), f"title={dub_title}"]

    # --- Sous-titres externes ---
    if add_subtitle and subtitle_srt_path:
        cmd += ["-metadata:s:s:{}".format(new_sub_out_index), "title=Français"]
        cmd += ["-c:s:{}".format(new_sub_out_index), sub_codec]

    # --- Dispositions ---
    if set_dub_default:
        cmd += ["-disposition:a", "0"]
        cmd += ["-disposition:a:{}".format(new_audio_out_index), "default"]
        cmd += ["-disposition:s", "0"]

    # --- Sortie ---
    cmd += [output_video_path]

    run_ffmpeg_with_percentage(cmd, duration_source=video_fullpath)
