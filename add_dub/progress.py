"""Événements GUI et estimation pondérée, sans dépendance Qt."""
from add_dub.gui.translations import ui
import json
import os
import math

PREFIX = '@@ADD_DUB_PROGRESS@@'
# Parts relatives, pas une mesure du temps restant. Les étapes facultatives
# sont ajoutées au plan uniquement lorsqu'elles seront réellement exécutées.
WEIGHTS = {'subtitles': 5, 'ocr': 40, 'translation': 30,
           'audio': 10, 'tts': 60, 'ducking': 5, 'mux': 20}
LABELS = {'subtitles': 'Extraction des sous-titres', 'ocr': 'OCR',
          'translation': 'Traduction', 'audio': 'Extraction audio',
          'tts': 'Génération vocale', 'ducking': 'Atténuation audio', 'mux': 'Mixage final'}


def emit(kind, **data):
    if os.getenv('ADD_DUB_GUI_PROGRESS') == '1':
        print('\n' + PREFIX + json.dumps({'event': kind, **data}), flush=True)


def stage(name):
    emit('stage', name=name)


class VideoProgress:
    def __init__(self):
        self.plan(False, False)

    def plan(self, subtitles, translation):
        self.weights = {key: value for key, value in WEIGHTS.items()
                        if key not in ('subtitles', 'ocr', 'translation')
                        or key == 'subtitles' and subtitles or key == 'translation' and translation}
        self.current = None
        self.done = set()
        self.percent = 0.0
        self.label = ui('Préparation')
        self.within = None

    @property
    def text(self):
        detail = ui('en cours') if self.within is None else f'{self.within:.0f} %'
        return f'{self.label} : {detail} · Total ≈ {int(self.percent)} %'

    def update(self, event):
        kind = event.get('event')
        if kind == 'plan':
            self.plan(event.get('subtitles', False), event.get('translation', False))
            if event.get('ocr'):
                self.weights['ocr'] = WEIGHTS['ocr']
        elif kind == 'include' and event.get('name') in WEIGHTS:
            self.weights.setdefault(event['name'], WEIGHTS[event['name']])
        elif kind == 'skip' and event.get('name') in self.weights:
            name = event['name']
            self.weights.pop(name)
            self.done.discard(name)
            if self.current == name:
                self.current = None
                self.within = None
            self._advance(self.within or 0)
        elif kind == 'stage' and event.get('name') in WEIGHTS:
            name = event['name']
            if self.current and name != self.current:
                self.done.add(self.current)
            self.weights.setdefault(name, WEIGHTS[name])
            self.current = name
            self.label = ui(LABELS[name])
            self.within = None
            self._advance(0)
        elif kind == 'progress' and self.current:
            try:
                value = float(event['value'])
            except (ValueError, TypeError, KeyError):
                return
            if math.isfinite(value):
                self.within = max(self.within or 0, max(0, min(100, value)))
                self._advance(self.within)

    def _advance(self, within):
        total = sum(self.weights.values()) or 1
        finished = sum(self.weights[k] for k in self.done)
        value = 100 * (finished + self.weights.get(self.current, 0) * within / 100) / total
        # 100 % est réservé à la sortie réussie du processus.
        self.percent = max(self.percent, min(99.9, value))


def aggregate(completed, total, current=0):
    return min(100.0, 100 * (completed + current / 100) / total) if total else 0.0


def remaining_seconds(durations, remaining, current_percent):
    if not durations:
        return None
    return max(0, sum(durations) / len(durations) * (remaining - current_percent / 100))
