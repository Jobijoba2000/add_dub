import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from add_dub.cli.args import parse_args, want_interactive
from add_dub.gui import FIELDS, BOOLS, batch_command


class ModesAndGuiTests(unittest.TestCase):
    def test_console_is_default_and_modes_are_exclusive(self):
        self.assertTrue(want_interactive(parse_args([])[0]))
        self.assertFalse(want_interactive(parse_args(['--gui'])[0]))
        with self.assertRaises(SystemExit):
            parse_args(['--gui', '--batch'])

    def test_gui_dispatch_is_lazy(self):
        from add_dub.__main__ import main
        with patch('add_dub.gui.main', return_value=0) as gui:
            self.assertEqual(main(['--gui']), 0)
            gui.assert_called_once()
        with patch('add_dub.cli.main.main', return_value=0) as console:
            self.assertEqual(main([]), 0)
            console.assert_called_once()

    def form(self):
        args = parse_args(['--gui'])[0]
        values = {name: '' if getattr(args, name) is None else str(getattr(args, name)) for name, _, _ in FIELDS}
        flags = {name: False for name in BOOLS}
        return values, flags

    def test_round_trip_paths_options_and_translation_disabled(self):
        values, flags = self.form()
        values.update(audio_bitrate='192', translation_engine='google', audio_index='2', sub='mkv:1')
        with tempfile.TemporaryDirectory(prefix='dub space ') as directory:
            command = batch_command(values, flags, [directory], directory)
        args, unknown = parse_args(command[command.index('--batch'):])
        self.assertFalse(unknown)
        self.assertEqual(args.input, [directory])
        self.assertFalse(args.translate)
        self.assertEqual(args.sub_index, 1)
        self.assertEqual(args.audio_index, 2)
        from add_dub.cli.batch import _make_options
        with patch('add_dub.cli.batch.resolve_voice_with_fallbacks', return_value='fr'):
            options = _make_options(args)
        self.assertEqual(options.translation_engine, 'google')
        self.assertIn('192k', options.audio_codec_args)
        self.assertTrue(all(isinstance(arg, str) for arg in options.audio_codec_args))

    def test_invalid_form_rejected_before_launch(self):
        for name, value in [('bg_mix', 'nan'), ('audio_index', '-1'), ('sub', 'oops'), ('min_rate_tts', '100')]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                values, flags = self.form()
                values[name] = value
                with self.assertRaises(ValueError):
                    batch_command(values, flags, [directory], directory)

    def test_frozen_command_uses_same_executable(self):
        import sys
        values, flags = self.form()
        with tempfile.TemporaryDirectory() as directory, patch.object(sys, 'frozen', True, create=True):
            command = batch_command(values, flags, [directory], directory)
        self.assertEqual(command[:2], [sys.executable, '--batch'])


class ConfigurationWindowTests(unittest.TestCase):
    def test_empty_folder_dialog_opens_and_closes(self):
        from PySide6.QtWidgets import QApplication
        from add_dub.gui_dialog import ConfigureDialog
        from add_dub.gui_model import Job, Settings
        from add_dub.gui_theme import apply_theme
        from unittest.mock import Mock

        app = QApplication.instance() or QApplication([])
        apply_theme(app)
        tasks = Mock()
        # Exécute uniquement la découverte locale ; aucun moteur vocal ni réseau.
        tasks.run.side_effect = lambda owner, work, done: done(work(), None)
        args = parse_args(['--gui'])[0]
        with tempfile.TemporaryDirectory() as directory:
            dialog = ConfigureDialog(Job([directory], Settings.from_args(args), directory), tasks)
            try:
                dialog.show()
                app.processEvents()
                self.assertTrue(dialog.isVisible())
                self.assertTrue(dialog.recursive.isVisible())
                self.assertTrue(dialog.tree.isEnabled())
                self.assertFalse(dialog.add.isEnabled())
                self.assertEqual(dialog.tree.topLevelItemCount(), 1)
                self.assertIn('Aucune vidéo admissible', dialog.scope.text())
                tasks.run.assert_called_once()
                dialog.reject()
                self.assertFalse(dialog.isVisible())
            finally:
                dialog.close()
                dialog.deleteLater()


if __name__ == '__main__':
    unittest.main()
