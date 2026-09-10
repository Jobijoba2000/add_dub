"""Widgets Qt accessibles et chargement asynchrone des catalogues de voix."""
from copy import deepcopy
import threading

from PySide6.QtCore import QObject, Signal, QLocale, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QComboBox, QLabel, QCheckBox,
    QLineEdit, QTabWidget, QScrollArea, QSpinBox, QDoubleSpinBox,
)
from shiboken6 import isValid
from add_dub.gui_model import FIELDS, Settings, adapt_settings


class Async(QObject):
    delivered = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.delivered.connect(self.deliver)

    def deliver(self, event):
        owner, callback, result, error = event
        if isValid(owner) and not getattr(owner, '_closed', False):
            callback(result, error)

    def run(self, owner, function, callback):
        def work():
            result, error = None, None
            try:
                result = function()
            except Exception as exc:
                error = str(exc)
            if isValid(self):
                self.delivered.emit((owner, callback, result, error))
        threading.Thread(target=work, daemon=True).start()


def combo(entries=(), name=''):
    box = QComboBox()
    box.setMinimumContentsLength(18)
    box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    box.setAccessibleName(name)
    for label, value in entries:
        box.addItem(label, value)
    return box


def choose(box, value):
    index = box.findData(value)
    box.setCurrentIndex(index if index >= 0 else (0 if box.count() else -1))


def page_form(tabs, title):
    content = QWidget()
    form = QFormLayout(content)
    form.setContentsMargins(18, 20, 18, 20)
    form.setVerticalSpacing(14)
    form.setHorizontalSpacing(18)
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
    form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setWidget(content)
    tabs.addTab(scroll, title)
    return form


class VoicePicker(QWidget):
    changed = Signal()

    def __init__(self, async_tasks, parent=None):
        super().__init__(parent)
        self.tasks = async_tasks
        self.cache = {}
        self.voices = []
        self.desired = ''
        self.preferred_language = 'fr'
        self.generation = 0
        self.loading = False
        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)
        form.setVerticalSpacing(14)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.engine = combo([('Windows OneCore · hors ligne', 'onecore'), ('Edge · en ligne', 'edge'), ('Google TTS · en ligne', 'gtts')], 'Moteur vocal')
        self.language = combo(name='Langue de la voix')
        self.region = combo(name='Variante régionale')
        self.voice = combo(name='Voix disponible')
        for label, widget in (('Moteur', self.engine), ('Langue', self.language), ('Région', self.region), ('Voix', self.voice)):
            form.addRow(label, widget)
        self.notice = QLabel()
        self.notice.setWordWrap(True)
        form.addRow(self.notice)
        self.engine.currentIndexChanged.connect(self.engine_changed)
        self.language.currentIndexChanged.connect(self.language_changed)
        self.region.currentIndexChanged.connect(self.region_changed)
        self.voice.currentIndexChanged.connect(self.changed)

    def set_value(self, engine, voice, preferred='fr'):
        self.preferred_language = preferred or 'fr'
        self.desired = voice or ''
        self.engine.blockSignals(True)
        choose(self.engine, engine)
        self.engine.blockSignals(False)
        self.load()

    def engine_changed(self):
        self.desired = ''
        self.load()
        self.changed.emit()

    def load(self):
        engine = self.engine.currentData()
        self.generation += 1
        generation = self.generation
        self.loading = True
        for box in (self.language, self.region, self.voice):
            box.blockSignals(True)
            box.clear()
            box.setEnabled(False)
            box.blockSignals(False)
        self.notice.setText('Recherche des langues et des voix…')
        def finish(voices, error):
            if generation != self.generation:
                return
            self.loading = False
            self.voices = voices or []
            if self.voices:
                self.cache[engine] = self.voices
            self.populate(error)
        if engine in self.cache:
            finish(self.cache[engine], None)
        else:
            def fetch():
                from add_dub.core.tts_registry import list_voices_for_engine
                return list_voices_for_engine(engine)
            self.tasks.run(self, fetch, finish)

    def populate(self, error):
        self.language.blockSignals(True)
        languages = sorted({v.get('lang', '').replace('_', '-').split('-')[0] for v in self.voices})
        for code in languages:
            locale = QLocale(code)
            label = locale.nativeLanguageName() or code or 'Langue inconnue'
            self.language.addItem(f'{label.capitalize()} ({code})', code)
        desired = next((v for v in self.voices if v['id'] == self.desired), None)
        code = desired['lang'].replace('_', '-').split('-')[0] if desired else self.preferred_language.split('-')[0]
        choose(self.language, code)
        self.language.setEnabled(bool(languages))
        self.language.blockSignals(False)
        self.language_changed()
        if error or not self.voices:
            self.notice.setText(error or 'Aucune voix disponible. Choisissez un autre moteur ou installez une voix Windows.')
        elif self.engine.currentData() == 'gtts':
            self.notice.setText('gTTS propose une voix par langue, sans choix de timbre.')
        elif self.engine.currentData() == 'edge' and len(self.voices) == 1:
            self.notice.setText('Catalogue Edge limité : connexion indisponible, voix de secours proposée.')
        else:
            self.notice.setText(f'{len(self.voices)} voix détectées pour ce moteur.')

    def language_changed(self):
        code = self.language.currentData()
        self.region.blockSignals(True)
        self.region.clear()
        locales = sorted({v.get('lang', '') for v in self.voices if v.get('lang', '').replace('_', '-').split('-')[0] == code})
        for locale_code in locales:
            locale = QLocale(locale_code)
            name = locale.nativeTerritoryName() if '-' in locale_code or '_' in locale_code else 'Variante unique'
            self.region.addItem(f'{name or locale_code} ({locale_code})', locale_code)
        desired = next((v for v in self.voices if v['id'] == self.desired), None)
        if desired:
            choose(self.region, desired['lang'])
        self.region.setEnabled(len(locales) > 1)
        self.region.blockSignals(False)
        self.region_changed()

    def region_changed(self):
        self.voice.blockSignals(True)
        self.voice.clear()
        for record in self.voices:
            if record.get('lang', '') == self.region.currentData():
                self.voice.addItem(record.get('display_name') or record['id'], record['id'])
        choose(self.voice, self.desired)
        self.voice.setEnabled(self.voice.count() > 0)
        self.voice.blockSignals(False)
        self.changed.emit()

    def value(self):
        return self.engine.currentData(), (self.desired if self.loading else self.voice.currentData()) or ''


class SettingsEditor(QTabWidget):
    changed = Signal()

    def __init__(self, tasks, parent=None):
        super().__init__(parent)
        self.loading = False
        self.base = None
        self.video = None
        self.setAccessibleName('Réglages du doublage')
        sources = page_form(self, 'Pistes et voix')
        self.audio = combo(name='Piste audio originale')
        self.sub = combo(name='Source des sous-titres')
        # Les intitulés longs peuvent utiliser l'espace disponible.
        self.audio.setMinimumContentsLength(26)
        self.sub.setMinimumContentsLength(26)
        sources.addRow('Audio original', self.audio)
        sources.addRow('Sous-titres', self.sub)
        self.voice = VoicePicker(tasks)
        sources.addRow(self.voice)
        trans = page_form(self, 'Traduction')
        self.translate = QCheckBox('Traduire les sous-titres avant le doublage')
        self.translation_engine = combo([('Traduction locale · CTranslate2', 'ctranslate2'), ('Google · en ligne', 'google')], 'Moteur de traduction')
        self.translate_to = QLineEdit()
        self.translate_to.setAccessibleName('Langue cible de traduction')
        self.translate_to.setMaximumWidth(160)
        self.translate_from = QLineEdit()
        self.translate_from.setAccessibleName('Langue source de traduction')
        self.translate_from.setPlaceholderText('Automatique')
        self.translate_from.setMaximumWidth(160)
        trans.addRow(self.translate)
        trans.addRow('Moteur', self.translation_engine)
        trans.addRow('Langue cible (fr, en…)', self.translate_to)
        trans.addRow('Langue source', self.translate_from)
        advanced = page_form(self, 'Audio et temps')
        self.fields = {}
        for key, label, choices in FIELDS[7:]:
            if choices:
                widget = combo([(x.upper(), x) for x in choices], label)
            elif key in ('audio_bitrate', 'offset_ms', 'offset_video_ms', 'limit_duration_sec'):
                widget = QSpinBox()
                widget.setRange(-3600000 if key.startswith('offset') else 0, 3600000)
                if key == 'limit_duration_sec':
                    widget.setSpecialValueText('Vidéo entière')
                if key == 'audio_bitrate':
                    widget.setMinimum(8)
                    widget.setMaximum(1536)
            else:
                widget = QDoubleSpinBox()
                widget.setRange(-100 if key == 'ducking_db' else 0.01 if key.endswith('rate_tts') else 0, 100)
                widget.setDecimals(2)
                widget.setSingleStep(0.1)
            widget.setAccessibleName(label)
            widget.setMaximumWidth(260)
            self.fields[key] = widget
            advanced.addRow(label.split(' ;')[0], widget)
        for widget in (self.audio, self.sub, self.translation_engine, *self.fields.values()):
            signal = widget.currentIndexChanged if isinstance(widget, QComboBox) else widget.valueChanged
            signal.connect(self.emit_change)
        self.voice.changed.connect(self.emit_change)
        self.translate.toggled.connect(self.translation_enabled)
        self.translate.toggled.connect(self.emit_change)
        self.translate_to.textChanged.connect(self.emit_change)
        self.translate_from.textChanged.connect(self.emit_change)

    def translation_enabled(self):
        for widget in (self.translation_engine, self.translate_to, self.translate_from):
            widget.setEnabled(self.translate.isChecked())

    def emit_change(self):
        if not self.loading:
            self.changed.emit()

    def load(self, settings, video):
        self.loading = True
        self.video = video
        self.base = adapt_settings(settings, video)
        for box, tracks, key in ((self.audio, video.audio, 'audio_index'), (self.sub, video.subtitles, 'sub')):
            box.clear()
            for track in tracks:
                box.addItem(track.label, track.value)
            choose(box, self.base.values[key])
            box.setToolTip(box.currentText())
        values = self.base.values
        self.translate.setChecked(self.base.translate)
        choose(self.translation_engine, values['translation_engine'])
        self.translate_to.setText(values['translate_to'])
        self.translate_from.setText(values['translate_from'])
        for key, widget in self.fields.items():
            if isinstance(widget, QComboBox):
                choose(widget, values[key])
            else:
                value = float(values[key] or 0)
                widget.setValue(int(value) if isinstance(widget, QSpinBox) else value)
        self.voice.set_value(values['tts_engine'], values['voice'], values['translate_to'])
        self.translation_enabled()
        self.loading = False

    def settings(self):
        result = deepcopy(self.base)
        if result is None:
            raise ValueError('Attendez la détection des pistes.')
        result.translate = self.translate.isChecked()
        for key, box in (('audio_index', self.audio), ('sub', self.sub), ('translation_engine', self.translation_engine)):
            result.values[key] = box.currentData() or ''
        result.audio = next((t for t in self.video.audio if t.value == result.values['audio_index']), None)
        result.subtitle = next((t for t in self.video.subtitles if t.value == result.values['sub']), None)
        result.values['tts_engine'], result.values['voice'] = self.voice.value()
        result.values['translate_to'] = self.translate_to.text().strip()
        result.values['translate_from'] = self.translate_from.text().strip()
        for key, widget in self.fields.items():
            value = widget.currentData() if isinstance(widget, QComboBox) else widget.value()
            result.values[key] = '' if key == 'limit_duration_sec' and value == 0 else str(value)
        return result
