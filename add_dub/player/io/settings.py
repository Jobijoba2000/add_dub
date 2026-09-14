"""Réglages de vocalisation propres au lecteur."""
import json
import math
import os
from pathlib import Path
from .fs import ROOT

SETTINGS_PATH = ROOT / 'player-data' / 'settings.json'
DEFAULTS = {'ducking_db': -5.0, 'min_rate_tts': 1.0, 'max_rate_tts': 1.8,
            'tts_mix': 1.0, 'bg_mix': 1.0}


def validated(settings):
    result = {**DEFAULTS, **settings}
    for key, low, high in [('ducking_db', -100, 0), ('min_rate_tts', .1, 10),
                           ('max_rate_tts', .1, 10), ('tts_mix', 0, 10), ('bg_mix', 0, 10)]:
        value = float(result[key])
        if not math.isfinite(value) or not low <= value <= high:
            raise ValueError('Valeur invalide : ' + key)
        result[key] = value
    if result['min_rate_tts'] > result['max_rate_tts']:
        raise ValueError('La vitesse minimale doit être inférieure ou égale à la vitesse maximale.')
    return result


def load_settings(path=SETTINGS_PATH):
    if not Path(path).exists():
        return None
    return validated(json.loads(Path(path).read_text(encoding='utf-8')))


def save_settings(settings, path=SETTINGS_PATH):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(validated(settings), ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporary, target)
