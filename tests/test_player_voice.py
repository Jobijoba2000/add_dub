"""Vérifie les quatre listes du composant repris, sans requête réseau."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from add_dub.player.io.settings import DEFAULTS, save_settings, load_settings
from PySide6.QtWidgets import QApplication, QDialogButtonBox
from add_dub.player.gui.voice_dialog import VoiceDialog

VOICES = [
    {'id': 'france-a', 'display_name': 'Voix France A', 'lang': 'fr-FR'},
    {'id': 'france-b', 'display_name': 'Voix France B', 'lang': 'fr-FR'},
    {'id': 'canada', 'display_name': 'Voix Canada', 'lang': 'fr-CA'},
    {'id': 'english', 'display_name': 'English', 'lang': 'en-US'},
]


class Tasks:
    def run(self, owner, function, callback):
        self.callback = callback


class VoiceDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tasks = Tasks()
        self.dialog = VoiceDialog(self.tasks)

    def tearDown(self):
        self.dialog.reject()
        self.dialog.deleteLater()
        self.app.processEvents()

    def test_language_region_voice_filter(self):
        self.tasks.callback(VOICES, None)
        picker = self.dialog.picker
        picker.language.setCurrentIndex(picker.language.findData('fr'))
        picker.region.setCurrentIndex(picker.region.findData('fr-FR'))
        self.assertEqual(picker.voice.count(), 2)
        picker.region.setCurrentIndex(picker.region.findData('fr-CA'))
        self.assertEqual(picker.voice.currentData(), 'canada')
        picker.language.setCurrentIndex(picker.language.findData('en'))
        self.assertEqual(picker.voice.currentData(), 'english')

    def test_loading_and_empty_catalog(self):
        button = self.dialog.buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.assertFalse(button.isEnabled())
        self.tasks.callback([], 'Catalogue indisponible')
        self.assertFalse(button.isEnabled())
        self.assertEqual(self.dialog.picker.notice.text(), 'Catalogue indisponible')

    def test_old_engine_result_is_ignored(self):
        old_callback = self.tasks.callback
        self.dialog.picker.engine.setCurrentIndex(1)
        old_callback(VOICES, None)
        self.assertTrue(self.dialog.picker.loading)
        self.tasks.callback([{'id': 'edge', 'display_name': 'Edge', 'lang': 'fr-FR'}], None)
        self.assertEqual(self.dialog.selection()['engine'], 'edge')
        self.assertEqual(self.dialog.selection()['voice'], 'edge')

    def test_restore_selection(self):
        self.dialog.picker.set_value('onecore', 'canada', 'fr')
        self.tasks.callback(VOICES, None)
        self.assertEqual(self.dialog.selection(), {**DEFAULTS, 'engine': 'onecore', 'language': 'fr', 'region': 'fr-CA', 'voice': 'canada'})

    def test_save_and_restore_all_settings(self):
        self.tasks.callback(VOICES, None)
        values = dict(ducking_db=-8, min_rate_tts=.9, max_rate_tts=1.6, tts_mix=1.2, bg_mix=.7)
        for key, value in values.items():
            self.dialog.fields[key].setValue(value)
        received = []
        self.dialog.settings_saved.connect(received.append)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'settings.json'
            with patch('add_dub.player.gui.voice_dialog.save_settings', side_effect=lambda s: save_settings(s, path)):
                self.dialog.save_button.click()
            saved = load_settings(path)
            self.assertEqual(saved, self.dialog.selection())
            self.assertEqual(received, [saved])
            restored = VoiceDialog(Tasks(), saved)
            for key, value in values.items():
                self.assertEqual(restored.fields[key].value(), value)
            restored.close()

    def test_minimum_cannot_exceed_maximum(self):
        self.tasks.callback(VOICES, None)
        self.dialog.fields['min_rate_tts'].setValue(3)
        self.assertFalse(self.dialog.save_button.isEnabled())
        self.assertFalse(self.dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled())


if __name__ == '__main__':
    unittest.main()
