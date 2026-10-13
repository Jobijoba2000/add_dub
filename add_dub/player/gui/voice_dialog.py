"""Fenêtre de sélection utilisant le VoicePicker d'add_dub."""
from add_dub.gui.translations import ui
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDialog, QVBoxLayout, QDialogButtonBox, QFormLayout, QDoubleSpinBox, QLabel, QMessageBox
from add_dub.player.io.settings import DEFAULTS, save_settings
from add_dub.gui.widgets import VoicePicker


class VoiceDialog(QDialog):
    settings_saved = Signal(dict)

    def __init__(self, tasks, settings=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(ui('Vocaliser les sous-titres'))
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(20)
        self.picker = VoicePicker(tasks, self)
        layout.addWidget(self.picker)
        settings = {**DEFAULTS, **(settings or {})}
        form = QFormLayout()
        self.fields = {}
        for key, title, low, high, suffix in [
                ('ducking_db', ui('Atténuation de l’original'), -100, 0, ' dB'),
                ('min_rate_tts', ui('Vitesse TTS minimale'), .1, 10, ' ×'),
                ('max_rate_tts', ui('Vitesse TTS maximale'), .1, 10, ' ×'),
                ('tts_mix', ui('Niveau TTS'), 0, 10, ' ×'),
                ('bg_mix', ui('Niveau du fond (BG)'), 0, 10, ' ×')]:
            field = QDoubleSpinBox()
            field.setRange(low, high)
            field.setDecimals(1 if key == 'ducking_db' else 2)
            field.setSingleStep(.1)
            field.setSuffix(suffix)
            field.setValue(settings[key])
            field.valueChanged.connect(self.refresh_validation)
            self.fields[key] = field
            form.addRow(title, field)
        layout.addLayout(form)
        self.notice = QLabel(ui('Niveaux : 1 = normal, 0 = muet. Lancement direct : Ctrl+Maj+D.'))
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText(ui('Générer le WAV'))
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(ui('Annuler'))
        self.save_button = self.buttons.addButton(ui('Enregistrer les réglages'), QDialogButtonBox.ButtonRole.ActionRole)
        self.save_button.clicked.connect(self.save)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.picker.changed.connect(self.refresh_validation)
        self.picker.set_value(settings.get('engine', 'onecore'), settings.get('voice', ''), settings.get('language', 'fr'))
        self.refresh_validation()

    def refresh_validation(self):
        if not hasattr(self, 'buttons'):
            return
        valid = (not self.picker.loading and bool(self.picker.voice.currentData())
                 and self.fields['min_rate_tts'].value() <= self.fields['max_rate_tts'].value())
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(
            valid)
        self.save_button.setEnabled(valid)
        if self.fields['min_rate_tts'].value() > self.fields['max_rate_tts'].value():
            self.notice.setText(ui('La vitesse minimale doit être inférieure ou égale à la vitesse maximale.'))
        else:
            self.notice.setText(ui('Niveaux : 1 = normal, 0 = muet. Lancement direct : Ctrl+Maj+D.'))

    def save(self):
        try:
            save_settings(self.selection())
            self.settings_saved.emit(self.selection())
            self.notice.setText(ui('Voix et réglages enregistrés. Lancement direct : Ctrl+Maj+D.'))
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, ui('Enregistrement impossible'), str(exc))

    def selection(self):
        engine, voice = self.picker.value()
        return {'engine': engine, 'language': self.picker.language.currentData(),
                'region': self.picker.region.currentData(), 'voice': voice,
                **{key: field.value() for key, field in self.fields.items()}}

    def done(self, result):
        self.picker._closed = True
        super().done(result)
