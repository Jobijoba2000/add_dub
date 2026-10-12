import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from add_dub.gui.general_settings import GeneralSettingsDialog
from add_dub.config.editor import read_settings


class ImmediateVoices:
    def run(self, owner, work, callback):
        callback([
            {'id': 'fr-test', 'lang': 'fr-FR', 'display_name': 'Voix française'},
            {'id': 'en-test', 'lang': 'en-GB', 'display_name': 'English voice'},
        ], None)


class GeneralSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / 'options.conf'
        self.path.write_text('# conserver\nvoice_id = "fr-test"\ntranslate = false d\n'
                             'bg = 1.0\n[logging]\nconsole_enable = false\n', encoding='utf-8')
        self.window = GeneralSettingsDialog(ImmediateVoices(), path=self.path)

    def tearDown(self):
        self.window.reject()
        self.window.deleteLater()
        self.app.processEvents()
        self.directory.cleanup()

    def test_cancel_preserves_file_and_dependencies_follow_switches(self):
        before = self.path.read_bytes()
        self.assertFalse(self.window.fields['translate_to'].isEnabled())
        self.assertFalse(self.window.fields['logging.console_level'].isEnabled())
        self.window.fields['translate'].setChecked(True)
        self.assertTrue(self.window.fields['translation_engine'].isEnabled())
        self.assertTrue(self.window.fields['reuse_translated_subs'].isEnabled())
        codec = self.window.fields['audio_codec']
        codec.setCurrentIndex(codec.findData('flac'))
        self.assertFalse(self.window.fields['audio_bitrate'].isEnabled())
        self.window.reject()
        self.assertEqual(self.path.read_bytes(), before)

    def test_numeric_errors_block_save_and_mark_tab_then_clear(self):
        field = self.window.fields['bg']
        field.editor.setText('20.0')
        self.assertFalse(self.window.save_button.isEnabled())
        self.assertFalse(field.isValid())
        self.assertTrue(self.window.tabs.tabText(2).startswith('! '))
        field.editor.setText('1,5')
        self.assertFalse(self.window.save_button.isEnabled())
        field.editor.setText('1.5')
        self.assertTrue(self.window.save_button.isEnabled())
        self.window.fields['min_rate_tts'].editor.setText('3.0')
        self.window.fields['max_rate_tts'].editor.setText('2.0')
        self.assertFalse(self.window.save_button.isEnabled())
        self.window.fields['max_rate_tts'].editor.setText('3.5')
        self.assertTrue(self.window.save_button.isEnabled())
        self.window.fields['offset'].editor.setText('1.5')
        self.assertFalse(self.window.save_button.isEnabled())

    def test_save_roundtrip_preserves_voice_comments_and_uses_dot(self):
        self.window.fields['bg'].editor.setText('1.5')
        self.window.fields['offset'].editor.setText('-125')
        self.window.fields['translate'].setChecked(True)
        self.window.save()
        self.assertIsNotNone(self.window.saved_values)
        data = read_settings(self.path)
        self.assertEqual(data['voice_id'], 'fr-test')
        self.assertEqual(float(data['bg']), 1.5)
        self.assertEqual(int(data['offset']), -125)
        self.assertTrue(data['translate'])
        text = self.path.read_text(encoding='utf-8')
        self.assertIn('# conserver', text)
        self.assertIn('translate = true d', text)

    def test_missing_voice_is_preserved_and_auto_choice_is_explicit(self):
        self.window.voice.set_value('onecore', 'missing-id', 'fr')
        self.assertEqual(self.window.values()['voice_id'], 'missing-id')
        self.window.automatic_voice.setChecked(True)
        self.assertEqual(self.window.values()['voice_id'], '')
        self.assertFalse(self.window.voice.language.isEnabled())
        self.window.automatic_voice.setChecked(False)
        self.assertEqual(self.window.values()['voice_id'], 'missing-id')

    def test_new_defaults_update_future_jobs_without_touching_existing(self):
        from add_dub.gui.application import Application
        from add_dub.cli.args import parse_args
        from add_dub.gui.model import Settings, Job
        with patch.dict(os.environ, {'ADD_DUB_OPTIONS': str(self.path)}), patch('add_dub.gui.application.fs.ensure_base_dirs'):
            window = Application(parse_args(['--gui'])[0])
            try:
                old = Job([], Settings.from_args(window.args), 'output')
                window.jobs = [old]
                self.window.fields['bg'].editor.setText('2.0')
                self.window.save()
                with patch('add_dub.gui.application.fs.set_base_dirs'), patch('add_dub.logger.reload_config'):
                    window.reload_defaults()
                self.assertEqual(window.args.bg_mix, 2.0)
                self.assertEqual(float(old.common.values['bg_mix']), 1.0)
                window.running = True
                window.refresh()
                self.assertFalse(window.settings_button.isEnabled())
            finally:
                window.running = False
                window.close()
                window.deleteLater()
