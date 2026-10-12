"""Édition des valeurs par défaut persistantes, indépendante des lots existants."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget, QLabel, QLineEdit,
    QPushButton, QTabWidget, QFormLayout, QFileDialog, QMessageBox, QComboBox,
)

from add_dub.config.editor import read_settings, save_settings, validate_settings, settings_path, number_limits
from add_dub.gui.widgets import VoicePicker, QueueTabBar, page_form, combo, choose
from add_dub.gui.settings_widgets import AnimatedToggle, NumberField


class DefaultVoicePicker(VoicePicker):
    """Garde visible une voix enregistrée même si son catalogue est indisponible."""
    def populate(self, error):
        super().populate(error)
        if self.desired and not any(v['id'] == self.desired for v in self.voices):
            self.voice.blockSignals(True)
            self.voice.addItem('Voix enregistrée (actuellement indisponible)', self.desired)
            self.voice.setCurrentIndex(self.voice.count() - 1)
            self.voice.blockSignals(False)
            self.notice.setText('La voix enregistrée est conservée. Vous pouvez choisir une autre voix ou le choix automatique.')
            self.changed.emit()


class GeneralSettingsDialog(QDialog):
    def __init__(self, tasks, parent=None, path=None):
        super().__init__(parent)
        self.path = Path(path) if path else settings_path()
        self.initial = read_settings(self.path)
        self.fields = {}
        self.labels = {}
        self.feedback = {}
        self.field_tabs = {}
        self._loading = True
        self._validating = False
        self.saved_values = None
        self._closed = False
        self.finished.connect(self._finish)
        self.setWindowTitle('Paramètres généraux — add_dub')
        self.resize(860, 740)
        self.setMinimumSize(700, 530)
        self.setStyleSheet('''
            QLabel[validationError="true"] { color: #ff8b8b; }
            QLineEdit[invalid="true"], QComboBox[invalid="true"] { border: 2px solid #f26c6c; }
            QLineEdit:disabled, QComboBox:disabled { color: #858585; background: #1a1a1a; border-color: #454545; }
            QLabel:disabled { color: #858585; }
            QPushButton:disabled { color: #858585; border-color: #454545; background: #202020; }
        ''')
        outer = QVBoxLayout(self)
        outer.setContentsMargins(22, 20, 22, 20)
        outer.setSpacing(14)
        title = QLabel('Paramètres généraux')
        title.setStyleSheet('font-size: 22px; font-weight: bold;')
        outer.addWidget(title)
        description = QLabel('Ces valeurs seront proposées pour les prochains ajouts de vidéos. '
                             'Les réglages propres aux lots déjà configurés sont conservés.')
        description.setWordWrap(True)
        outer.addWidget(description)
        self.tabs = QTabWidget()
        self.tabs.setObjectName('settingsTabs')
        bar = QueueTabBar(self.tabs)
        bar.setObjectName('queueTabs')
        bar.setExpanding(False)
        bar.setDrawBase(False)
        self.tabs.setTabBar(bar)
        outer.addWidget(self.tabs, 1)

        general = self._page('Général')
        for key, label in (('input_dir', 'Dossier d’entrée'), ('output_dir', 'Dossier de sortie'), ('tmp_dir', 'Fichiers temporaires')):
            self._path(general, key, label)
        self._choice(general, 'language', 'Langue des messages', [
            ('Automatique', 'auto'), ('Français', 'fr'), ('English', 'en'),
            ('Español', 'es'), ('Deutsch', 'de'), ('Italiano', 'it')])
        self._note(general, 'La langue concerne les messages du moteur et la console. Les libellés du GUI restent en français.')
        self._toggle(general, 'ask_test_before_cleanup', 'Proposer un essai avant nettoyage')
        self._note(general, 'Cette demande concerne le mode console interactif. Dans le GUI, utilisez l’onglet Essai du configurateur.')

        voices = self._page('Voix')
        self.automatic_voice = AnimatedToggle('Choisir automatiquement la voix')
        self.automatic_voice.setChecked(not self.initial.get('voice_id'))
        voices.addRow(self.automatic_voice)
        self.voice = DefaultVoicePicker(tasks)
        voices.addRow(self.voice)
        self.voice_error = QLabel()
        self.voice_error.setWordWrap(True)
        self.voice_error.setProperty('validationError', True)
        voices.addRow(self.voice_error)
        self.field_tabs.update(tts_engine=1, voice_id=1)
        self._note(voices, 'Le même catalogue de voix est utilisé lors de l’ajout d’une vidéo.')
        for key, label in (('min_rate_tts', 'Vitesse minimale'), ('max_rate_tts', 'Vitesse maximale')):
            self._number(voices, key, label, suffix=' ×')
        self._note(voices, '1.0 = vitesse normale. OneCore accepte 0.5 à 6.0 ; les autres moteurs sont limités ici à 0.1–10.0. '
                           'La vitesse minimale doit rester inférieure ou égale à la maximale.')

        audio = self._page('Audio et temps')
        self._choice(audio, 'audio_codec', 'Codec audio', [(label, value) for label, value in (
            ('AC3', 'ac3'), ('AAC', 'aac'), ('MP3', 'mp3'), ('Opus', 'opus'),
            ('Vorbis', 'vorbis'), ('FLAC · sans perte', 'flac'), ('PCM 16 bits · sans perte', 'pcm_s16le'))])
        self._number(audio, 'audio_bitrate', 'Débit audio', integer=True, suffix=' kbit/s')
        self._number(audio, 'db', 'Atténuation du fond', suffix=' dB')
        self._number(audio, 'bg', 'Volume original', suffix=' ×')
        self._number(audio, 'tts', 'Volume des voix', suffix=' ×')
        self._number(audio, 'offset', 'Décalage des sous-titres', integer=True, suffix=' ms')
        self._number(audio, 'offset_video', 'Décalage vidéo', integer=True, suffix=' ms')
        self._text(audio, 'orig_audio_lang', 'Libellé audio original')
        self._note(audio, 'Les décalages et le débit utilisent des entiers. Les volumes, vitesses et dB utilisent une décimale avec un point. '
                          'Les plages affichées limitent les valeurs saisies ; les volumes supérieurs à 1.0 amplifient le son.')

        translation = self._page('Traduction')
        self._toggle(translation, 'translate', 'Traduire avant le doublage')
        self._choice(translation, 'translation_engine', 'Moteur de traduction', [
            ('CTranslate2 · local', 'ctranslate2'), ('Google · en ligne', 'google')])
        self._text(translation, 'translate_from', 'Langue source', 'auto, fr, en…')
        self._text(translation, 'translate_to', 'Langue cible', 'fr, en, es…')
        self._toggle(translation, 'reuse_translated_subs', 'Réutiliser les traductions existantes')
        self._note(translation, 'La désactivation conserve les réglages pour la prochaine activation. '
                                'CTranslate2 traduit localement ; Google reçoit le texte à traduire.')

        logs = self._page('Journal')
        self._toggle(logs, 'logging.console_enable', 'Afficher les messages en console')
        levels = [(name, name) for name in ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')]
        self._choice(logs, 'logging.console_level', 'Niveau console', levels)
        self._toggle(logs, 'logging.file_enable', 'Enregistrer un journal dans un fichier')
        self._choice(logs, 'logging.file_level', 'Niveau du fichier', levels)
        self._path(logs, 'logging.dir', 'Dossier du journal')
        self._text(logs, 'logging.file_name', 'Nom du fichier journal')

        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setAccessibleName('Validation des paramètres')
        outer.addWidget(self.status)
        footer = QHBoxLayout()
        location = QLabel(str(self.path))
        location.setWordWrap(True)
        location.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        location.setStyleSheet('color: #aaa; font-size: 11px;')
        footer.addWidget(location, 1)
        self.cancel_button = QPushButton('Annuler')
        self.cancel_button.clicked.connect(self.reject)
        self.save_button = QPushButton('Enregistrer')
        self.save_button.setObjectName('primary')
        self.save_button.clicked.connect(self.save)
        footer.addWidget(self.cancel_button)
        footer.addWidget(self.save_button)
        outer.addLayout(footer)
        self.automatic_voice.toggled.connect(self.validate)
        self.voice.changed.connect(self.validate)
        self.voice.set_value(self.initial['tts_engine'], self.initial.get('voice_id', ''), self.initial.get('translate_to', 'fr'))
        self._loading = False
        self.validate()

    def _page(self, title):
        form = page_form(self.tabs, title)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setVerticalSpacing(18)
        return form

    def _note(self, form, text):
        note = QLabel(text)
        note.setWordWrap(True)
        note.setStyleSheet('color: #b5b5b5;')
        form.addRow(note)

    def _register(self, form, key, label, widget, row=None):
        self.fields[key] = widget
        self.field_tabs[key] = self.tabs.count() - 1
        caption = QLabel(label)
        caption.setBuddy(widget.editor if isinstance(widget, NumberField) else widget)
        self.labels[key] = caption
        widget.setAccessibleName(label)
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(row or widget)
        error = QLabel()
        error.setWordWrap(True)
        error.setProperty('validationError', True)
        error.hide()
        self.feedback[key] = error
        if not isinstance(widget, NumberField):
            layout.addWidget(error)
        form.addRow(caption, panel)
        signal = widget.changed if isinstance(widget, NumberField) else widget.toggled if isinstance(widget, AnimatedToggle) else widget.currentIndexChanged if isinstance(widget, QComboBox) else widget.textChanged
        signal.connect(self.validate)

    def _text(self, form, key, label, placeholder=''):
        widget = QLineEdit(str(self.initial.get(key, '') or ''))
        widget.setPlaceholderText(placeholder)
        self._register(form, key, label, widget)

    def _path(self, form, key, label):
        field = QLineEdit(str(self.initial.get(key, '')))
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(field, 1)
        browse = QPushButton('Parcourir…')
        browse.setAutoDefault(False)
        def select():
            directory = QFileDialog.getExistingDirectory(self, label, field.text())
            if directory:
                field.setText(directory)
        browse.clicked.connect(select)
        field._browse = browse
        layout.addWidget(browse)
        self._register(form, key, label, field, row)

    def _choice(self, form, key, label, entries):
        field = combo(entries, label)
        value = self.initial.get(key)
        if field.findData(value) < 0:
            field.addItem(str(value), value)
        choose(field, value)
        self._register(form, key, label, field)

    def _toggle(self, form, key, label):
        field = AnimatedToggle()
        field.setChecked(self.initial.get(key) is True)
        self._register(form, key, label, field)

    def _number(self, form, key, label, integer=False, suffix=''):
        low, high = number_limits(key, self.initial)
        field = NumberField(low, high, integer=integer, suffix=suffix)
        field.setValue(self.initial[key])
        self._register(form, key, label, field)

    def values(self):
        values = dict(self.initial)
        for key, field in self.fields.items():
            if isinstance(field, NumberField):
                values[key] = field.text()
            elif isinstance(field, AnimatedToggle):
                values[key] = field.isChecked()
            elif isinstance(field, QComboBox):
                values[key] = field.currentData()
            else:
                values[key] = field.text().strip()
        values['tts_engine'], values['voice_id'] = self.voice.value()
        if self.automatic_voice.isChecked():
            values['voice_id'] = ''
        return values

    def _enable(self, key, enabled):
        widget = self.fields[key]
        widget.setEnabled(enabled)
        self.labels[key].setEnabled(enabled)
        if hasattr(widget, '_browse'):
            widget._browse.setEnabled(enabled)

    def validate(self, *_):
        if self._loading or self._validating:
            return
        self._validating = True
        try:
            values = self.values()
            for key in ('translation_engine', 'translate_from', 'translate_to', 'reuse_translated_subs'):
                self._enable(key, values['translate'])
            self._enable('logging.console_level', values['logging.console_enable'])
            for key in ('logging.file_level', 'logging.file_name', 'logging.dir'):
                self._enable(key, values['logging.file_enable'])
            self._enable('audio_bitrate', values['audio_codec'] not in ('flac', 'pcm_s16le'))
            for field in (self.voice.language, self.voice.region, self.voice.voice):
                minimum = 1 if field is self.voice.region else 0
                field.setEnabled(not self.automatic_voice.isChecked() and not self.voice.loading and field.count() > minimum)
            errors = validate_settings(values)
            if not self.automatic_voice.isChecked() and not values['voice_id']:
                errors['voice_id'] = 'Chargement des voix…' if self.voice.loading else 'Choisissez une voix disponible ou activez le choix automatique.'
            message = errors.get('voice_id', '') or errors.get('tts_engine', '')
            self.voice_error.setText(message)
            self.voice_error.setVisible(bool(message))
            for key, field in self.fields.items():
                if isinstance(field, NumberField):
                    field.setRange(*number_limits(key, values))
                    field.setError(errors.get(key, ''))
                    if field.isEnabled() and not field.isValid():
                        errors[key] = field.errorText()
                else:
                    message = errors.get(key, '')
                    field.setProperty('invalid', bool(message))
                    field.style().unpolish(field)
                    field.style().polish(field)
                    self.feedback[key].setText(message)
                    self.feedback[key].setVisible(bool(message))
            for index in range(self.tabs.count()):
                base = self.tabs.tabText(index).removeprefix('! ')
                invalid = any(self.field_tabs.get(key) == index for key in errors)
                self.tabs.setTabText(index, ('! ' if invalid else '') + base)
            self.save_button.setEnabled(not errors)
            self.status.setText('Corrigez les champs signalés en rouge avant d’enregistrer.' if errors else
                                'Les modifications seront enregistrées dans options.conf.')
            self.status.setStyleSheet('color: #ff8b8b;' if errors else 'color: #b5b5b5;')
            return not errors
        finally:
            self._validating = False

    def save(self):
        if not self.validate():
            return
        try:
            values = self.values()
            save_settings(values, self.path)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, 'Enregistrement impossible', str(exc))
            return
        self.saved_values = read_settings(self.path)
        self.accept()

    def _finish(self, *_):
        self._closed = True
        self.voice._closed = True
