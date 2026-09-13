"""Préparation d’un extrait GUI dans son dossier temporaire dédié."""
import math
import subprocess
from pathlib import Path
from add_dub.adapters.ffmpeg import run_ffmpeg_with_percentage
from add_dub.progress import emit


def clipped_subtitles(subtitles, start, end):
    if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end):
        raise ValueError('La fin doit être supérieure au début.')
    return [(max(a, start) - start, min(b, end) - start, text)
            for a, b, text in subtitles if b > start and a < end]


def prepare_excerpt(source, srt, audio_index, start, end, directory, progress_cb=None):
    from add_dub.core.subtitles import parse_srt_file
    from add_dub.core.translation import write_srt_file
    subtitles = clipped_subtitles(parse_srt_file(srt), start, end)
    if not subtitles:
        raise ValueError('Aucun dialogue dans cette plage. Choisissez une autre portion.')
    directory = Path(directory)
    excerpt = directory / 'preview-source.mkv'
    excerpt_srt = directory / 'preview-source.srt'
    write_srt_file(subtitles, str(excerpt_srt))
    command = ['ffmpeg', '-nostdin', '-v', 'error', '-y', '-ss', str(start), '-i', source,
               '-t', str(end - start), '-map', '0:v:0', '-map', f'0:{audio_index}',
               '-c', 'copy', '-sn', '-avoid_negative_ts', 'make_zero', '-progress', 'pipe:1',
               str(excerpt)]
    try:
        run_ffmpeg_with_percentage(command, source, progress_cb=progress_cb,
                                   duration_override=end - start)
    except subprocess.CalledProcessError as error:
        raise RuntimeError(f'Extraction de l’extrait impossible (code {error.returncode}).') from error
    emit('preview_extract', value=100.0)
    return str(excerpt), str(excerpt_srt), 1
