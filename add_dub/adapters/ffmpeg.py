import json
import subprocess
from pathlib import Path
from add_dub.core.options import DubOptions
from add_dub.logger import (log_call, log_time)


def probe_media(path):
    result = subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-show_format',
                             '-of', 'json', str(path)], capture_output=True, text=True,
                            encoding='utf-8', errors='replace', timeout=30, check=True)
    return json.loads(result.stdout)


def media_duration(path):
    return float(probe_media(path).get('format', {}).get('duration', 0))


def validate_media(path):
    import math
    info = probe_media(path)
    streams = info.get('streams', [])
    duration = float(info.get('format', {}).get('duration', 0))
    if (not math.isfinite(duration) or duration <= 0 or
            not any(s.get('codec_type') == 'video' for s in streams) or
            sum(s.get('codec_type') == 'audio' for s in streams) < 2 or
            not any(s.get('codec_type') == 'subtitle' for s in streams)):
        raise ValueError(f'Sortie incomplète ou invalide : {path}')
    return info


def run_ffmpeg_with_percentage(cmd, duration_source, progress_cb=None, duration_override=None):
    """Lit les deux flux sans blocage et conserve un diagnostic borné."""
    from collections import deque
    import threading
    import time
    try:
        duration = float(duration_override) if duration_override is not None else media_duration(duration_source)
    except (ValueError, OSError, subprocess.SubprocessError):
        duration = 0
    cmd = list(cmd)
    if '-nostdin' not in cmd:
        cmd.insert(1, '-nostdin')
    errors = deque(maxlen=80)
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, encoding='utf-8', errors='replace', bufsize=1)
    last_activity = [time.monotonic()]
    stopped = threading.Event()
    timed_out = []

    def read_errors():
        for line in p.stderr:
            errors.append(line[-2000:])
            last_activity[0] = time.monotonic()

    def watchdog():
        while not stopped.wait(1):
            if time.monotonic() - last_activity[0] > 300:
                timed_out.append(True)
                p.kill()
                return

    reader = threading.Thread(target=read_errors, daemon=True)
    guard = threading.Thread(target=watchdog, daemon=True)
    reader.start()
    guard.start()
    try:
        for line in p.stdout:
            last_activity[0] = time.monotonic()
            if line.startswith('out_time_ms=') and duration > 0:
                try:
                    percent = min(99.9, max(0, float(line.split('=', 1)[1]) / (duration * 10000)))
                    if progress_cb:
                        progress_cb(percent)
                except ValueError:
                    pass
        rc = p.wait()
        reader.join()
        if rc or timed_out:
            detail = ''.join(errors)[-8000:]
            raise RuntimeError(f'FFmpeg a échoué (code {rc}, timeout={bool(timed_out)}) : {detail}')
        if progress_cb:
            progress_cb(100)
    finally:
        if p.poll() is None:
            p.kill()
            p.wait()
        stopped.set()
        reader.join(timeout=5)
        guard.join(timeout=2)
        p.stdout.close()
        p.stderr.close()

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
        text=True, encoding="utf-8", errors="replace", timeout=30, check=True
    )
    data = json.loads(result.stdout) if result.stdout else {}
    audio_tracks = []
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "audio":
            audio_tracks.append(stream)
    return audio_tracks

@log_time
@log_call()
def extract_audio_track(video_fullpath, audio_track_index, output_wav, duration_sec=None, progress_cb=None):
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
        "-ac", "2",
        "-c:a", "pcm_s16le",
    ]
    if duration_sec is not None:
        cmd.extend(["-t", str(int(duration_sec))])
    cmd.append(output_wav)

    # subprocess.run(cmd, check=True)
    run_ffmpeg_with_percentage(cmd, duration_source=video_fullpath, progress_cb=progress_cb)
    return output_wav






@log_time
@log_call(exclude="subtitle_srt_path")
def _dub_in_one_pass(
    *,
    video_fullpath: str,
    bg_wav: str,                 # audio1_wav (BG)
    tts_wav: str,                # audio2_wav (TTS)
    original_wav: str,           # WAV de l'audio d'origine (déjà extrait)
    subtitle_srt_path: str,
    output_video_path: str,
    opts: DubOptions,
    progress_cb=None,
    duration_sec=None,
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
    from add_dub.core.languages import language_name, dubbed_track_title
    dub_title = dubbed_track_title(opts.dubbed_language, opts.dubbed_locale)
    orig_title = language_name(opts.original_language)
    sub_title = language_name(opts.subtitle_language)

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
        f"[bg][tts]amix=inputs=2:duration=longest:dropout_transition=0:normalize=0,alimiter=limit=0.95:level=0:latency=1[a_mix]"
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
        "-map", "3:a:0",     # audio 1 (original réencodé depuis le WAV)
        "-map", "4:0",       # sous-titres

    ] + copy_video + [
        # Audio: même codec/paramètres pour TOUTES les pistes audio
        # (audio_codec_args est appliqué globalement à -c:a)
        *mix_codec_args(opts),
        # Force stéréo pour la piste audio 1 (original encodé), la 0 sort déjà en stéréo du mix
        "-ac:a:1", "2",

        # Codec des sous-titres
        "-c:s:0", opts.sub_codec,

        # Dispositions
        "-disposition:a:0", "default",
        "-disposition:a:1", "0",
        "-disposition:s:0", "0",

        # Métadonnées de langue : les WAV/SRT intermédiaires ont perdu les tags.
        "-metadata:s:a:0", f"language={opts.dubbed_language}",
        "-metadata:s:a:1", f"language={opts.original_language}",
        "-metadata:s:s:0", f"language={opts.subtitle_language}",
        # Métadonnées
        "-metadata:s:a:0", f"title={dub_title}",
        "-metadata:s:a:1", f"title={orig_title}",
        "-metadata:s:s:0", f"title={sub_title}",

        # Sortie finale
        output_video_path,
    ]

    if duration_sec is not None:
        cmd[-1:-1] = ['-t', str(duration_sec)]
    # Barre de progression (basée sur la durée vidéo)
    run_ffmpeg_with_percentage(cmd, duration_source=video_fullpath, progress_cb=progress_cb)
    return output_video_path


def mix_codec_args(opts):
    from add_dub.core.codecs import final_audio_codec_args
    args = final_audio_codec_args(opts.audio_codec, f'{int(opts.audio_bitrate)}k')
    return args


def dub_in_one_pass(**kwargs):
    """Ne publie jamais un MKV partiel, quel que soit le mode d'interface."""
    import os
    import tempfile
    from add_dub.io.work import publish
    from add_dub.core.validation import validate_options
    validate_options(kwargs['opts'])
    target = Path(kwargs['output_video_path']).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not kwargs['opts'].overwrite:
        raise FileExistsError(f'Sortie existante : {target}')
    gui_partial = os.environ.get('ADD_DUB_GUI_PARTIAL_OUTPUT')
    if gui_partial and target == Path(gui_partial).resolve():
        # Ce chemin est déjà la sortie provisoire connue du superviseur GUI.
        # Pas de deuxième fichier caché qui survivrait à un arrêt forcé.
        try:
            _dub_in_one_pass(**kwargs)
            validate_media(target)
            return str(target)
        except BaseException:
            target.unlink(missing_ok=True)
            raise
    fd, temporary = tempfile.mkstemp(prefix='.add_dub-', suffix='.partial.mkv', dir=target.parent)
    os.close(fd)
    try:
        _dub_in_one_pass(**{**kwargs, 'output_video_path': temporary})
        validate_media(temporary)
        publish(temporary, target, overwrite=kwargs['opts'].overwrite)
        return str(target)
    finally:
        Path(temporary).unlink(missing_ok=True)
