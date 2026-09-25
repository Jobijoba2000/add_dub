"""Validation commune aux interfaces et au moteur."""
import math


def validate_numbers(values):
    positive = {'audio_bitrate', 'min_rate_tts', 'max_rate_tts', 'limit_duration_sec'}
    nonnegative = {'audio_index', 'audio_ffmpeg_index', 'bg_mix', 'tts_mix'}
    numeric = positive | nonnegative | {'ducking_db', 'db_reduct', 'offset_ms', 'offset_video_ms'}
    for name in numeric:
        value = values.get(name)
        if value is None:
            continue
        if not math.isfinite(float(value)):
            raise ValueError(f'{name} doit être un nombre fini.')
        if name in positive and float(value) <= 0:
            raise ValueError(f'{name} doit être strictement positif.')
        if name in nonnegative and float(value) < 0:
            raise ValueError(f'{name} doit être positif ou nul.')
    if values.get('min_rate_tts', 1) > values.get('max_rate_tts', 1.8):
        raise ValueError('La vitesse minimale dépasse la vitesse maximale.')
    if values.get('overwrite') and values.get('skip_existing'):
        raise ValueError('Remplacer et ignorer les sorties sont incompatibles.')


def validate_options(opts):
    validate_numbers(vars(opts))
    from .codecs import final_audio_codec_args
    final_audio_codec_args(opts.audio_codec, None)
