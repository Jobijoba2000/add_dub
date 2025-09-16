# src/add_dub/adapters/ffmpeg.py
import os
import json
import time
import subprocess


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


def extract_audio_track(video_fullpath, audio_track_index, output_wav, duration_sec=None):
    """
    Extrait la piste audio ffmpeg index 'audio_track_index' en WAV PCM 16-bit.
    """
    cmd = [
        "ffmpeg", "-y",
        "-hide_banner", "-loglevel", "error", "-stats",
        "-i", video_fullpath,
        "-map", f"0:{audio_track_index}",
        "-vn",
        "-c:a", "pcm_s16le",
    ]
    if duration_sec is not None:
        cmd.extend(["-t", str(int(duration_sec))])
    cmd.append(output_wav)

    start = time.perf_counter()
    subprocess.run(cmd, check=True)
    end = time.perf_counter()
    print(end - start)
    return output_wav


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
        "-hide_banner", "-loglevel", "error", "-stats",
        "-i", audio1_wav,
        "-i", audio2_wav,
        "-filter_complex", filter_str,
        "-map", "[aout]",
    ] + list(audio_codec_args) + [
        output_file
    ]

    start = time.perf_counter()
    subprocess.run(cmd, check=True)
    end = time.perf_counter()
    print(end - start)
    return output_file


def encode_original_audio_to_final_codec(original_wav, output_audio, audio_codec_args):
    """
    Réencode l'audio d'origine (WAV) vers le codec final (args fournis),
    pour l'ajouter comme deuxième piste audio.
    """
    cmd = [
        "ffmpeg", "-y",
        "-hide_banner", "-loglevel", "error", "-stats",
        "-i", original_wav,
        "-ac", "2",
    ] + list(audio_codec_args) + [
        output_audio
    ]

    start = time.perf_counter()
    subprocess.run(cmd, check=True)
    end = time.perf_counter()
    print(end - start)
    return output_audio


def merge_to_container(
    video_fullpath,
    mixed_audio_file,
    orig_audio_encoded_file,
    subtitle_srt_path,
    output_video_path,
    orig_audio_name_for_title,
    sub_codec,
):
    """
    Fusionne :
      - Vidéo originale (copiée)
      - Piste audio 0 : mix TTS (par défaut)  -> title: "<orig> doublé en Français"
      - Piste audio 1 : audio original (même codec) -> title: "<orig>"
      - Piste sous-titres : présente mais non par défaut -> title: "Français"
    Pas de -shortest pour garder toute la durée.
    """
    inputs = [
        "-i", video_fullpath,            # 0
        "-i", mixed_audio_file,          # 1
        "-i", orig_audio_encoded_file,   # 2
        "-i", subtitle_srt_path,         # 3
    ]

    dub_title = f"{orig_audio_name_for_title} doublé en Français"
    orig_title = orig_audio_name_for_title
    sub_title = "Français"

    cmd = [
        "ffmpeg", "-y",
        "-hide_banner", "-loglevel", "error", "-stats",
    ] + inputs + [
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-map", "2:a:0",
        "-map", "3:0",
        "-c:v", "copy",
        "-c:a:0", "copy",
        "-c:a:1", "copy",
        "-c:s:0", sub_codec,
        "-disposition:a:0", "default",
        "-disposition:a:1", "0",
        "-disposition:s:0", "0",
        "-metadata:s:a:0", f"title={dub_title}",
        "-metadata:s:a:1", f"title={orig_title}",
        "-metadata:s:s:0", f"title={sub_title}",
        output_video_path,
    ]

    start = time.perf_counter()
    subprocess.run(cmd, check=True)
    end = time.perf_counter()
    print(end - start)
    return output_video_path
