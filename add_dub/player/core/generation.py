"""Entrée du processus TTS : extraction puis pipeline WAV d'add_dub."""
import json
import os
from pathlib import Path
import traceback
from add_dub.player.io import fs
from add_dub.progress import emit
from add_dub.player.io.settings import validated


class ProgressUI:
    def message(self, text):
        emit('message', text=text)

    def error(self, text):
        emit('message', text=text)

    def progress(self, percent):
        if percent >= 100:
            emit('finalizing', name='tts')
            return
        emit('progress', value=percent)


def main(request_path):
    fs.ensure_base_dirs()
    # Configure FFmpeg before importing pydub, including in spawned workers
    # through the inherited PATH/TMP environment.
    from add_dub.adapters.ffmpeg import extract_audio_track
    from add_dub.core.subtitles import resolve_srt_for_video, strip_subtitle_tags_inplace, parse_srt_file
    from add_dub.core.tts_generate import generate_dub_audio
    from add_dub.core.ducking import lower_audio_during_subtitles
    from add_dub.core.options import DubOptions
    from add_dub.io import fs as shared_fs
    # Ce processus ne prépare que les WAV du lecteur. Les chemins partagés
    # sont isolés ici, sans modifier ceux du GUI ou du mode batch.
    shared_fs.TMP_DIR = str(fs.TMP_DIR)
    shared_fs.SRT_DIR = str(fs.TMP_DIR)
    try:
        request = json.loads(Path(request_path).read_text(encoding='utf-8'))
        emit('stage', name='srt', text='Extraction SRT')
        choice = ('mkv', request['ordinal']) if Path(request['video']).suffix.lower() == '.mkv' else ('stream', request['ff_index'])
        srt = resolve_srt_for_video(request['video'], choice, ui=ProgressUI())
        if not srt:
            raise ValueError('Impossible d’extraire les sous-titres sélectionnés.')
        strip_subtitle_tags_inplace(str(srt))
        if not parse_srt_file(str(srt)):
            raise ValueError('La piste sélectionnée ne contient aucun sous-titre vocalisable.')
        emit('complete', name='srt')
        duration_ms = request['duration_ms']
        if duration_ms <= 0:
            raise ValueError('La durée de cette vidéo est indisponible.')
        settings = validated(request['settings'])
        opts = DubOptions(tts_engine=settings['engine'], voice_id=settings['voice'],
                          dubbed_language=settings['language'], dubbed_locale=settings['region'],
                          min_rate_tts=settings['min_rate_tts'], max_rate_tts=settings['max_rate_tts'],
                          db_reduct=settings['ducking_db'])
        emit('stage', name='tts', text='Génération TTS')
        temporary_wav = Path(fs.TMP_DIR) / 'dub.wav'
        generate_dub_audio(str(srt), str(temporary_wav), opts,
                           target_total_duration_ms=duration_ms, ui=ProgressUI())
        os.replace(temporary_wav, request['output'])
        emit('complete', name='tts')
        emit('stage', name='audio', text='Extraction audio')
        original_wav = Path(fs.TMP_DIR) / 'original.wav'
        extract_audio_track(request['video'], request['audio_ff_index'], str(original_wav),
                            progress_cb=lambda value: emit('progress', value=value))
        emit('complete', name='audio')
        cues = parse_srt_file(str(srt))
        emit('stage', name='ducking', text='Ducking audio')
        lower_audio_during_subtitles(str(original_wav), cues, request['original_output'],
                                     reduction_db=opts.db_reduct, fade_duration=0, offset_ms=0)
        emit('complete', name='ducking')
        emit('result', path=request['output'], original_path=request['original_output'])
        return 0
    except Exception as exc:
        traceback.print_exc()
        emit('error', text=str(exc))
        return 1
