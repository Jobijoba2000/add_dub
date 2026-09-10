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
    def test_twelve_selected_survive_late_detection_and_validation(self):
        from copy import deepcopy
        from unittest.mock import Mock
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication
        from add_dub.gui_dialog import ConfigureDialog
        from add_dub.gui_model import Job, Settings, Video, Track

        app = QApplication.instance() or QApplication([])
        args = parse_args(['--gui', '--tts-engine', 'gtts', '--voice', 'fr'])[0]
        tasks = Mock()
        with tempfile.TemporaryDirectory() as directory:
            videos = [Video(str(Path(directory) / f'{i}.mkv'), directory,
                            [Track('0', 'Audio', kind='audio')],
                            [Track('srt', 'SRT', kind='srt')]) for i in range(127)]
            job = Job([directory], Settings.from_args(args), str(Path(directory) / 'out'), videos=videos)
            for video in videos:
                Path(video.path).touch()
            dialog = ConfigureDialog(job, tasks)
            try:
                dialog.show()
                app.processEvents()
                dialog.build_tree()
                folder = dialog.tree.topLevelItem(1)
                first = dialog.file_items[videos[0].path]
                dialog.select_item(first, None)
                _, work, callback = tasks.run.call_args.args
                stale_result = deepcopy(dialog.job.videos[0])
                folder.setCheckState(0, Qt.CheckState.Unchecked)
                for video in videos[1:13]:
                    dialog.file_items[video.path].setCheckState(0, Qt.CheckState.Checked)
                with patch.object(dialog.editor, 'load'):
                    callback(stale_result, None)
                self.assertFalse(dialog.job.videos[0].selected)
                folder.setText(0, 'Dossier renommé dans la vue')
                folder.setExpanded(False)
                folder.setExpanded(True)
                self.assertEqual(len(dialog.job.selected), 12)
                with patch.object(dialog, 'save_current'), patch('add_dub.gui_dialog.QMessageBox.warning') as warning:
                    dialog.validate()
                self.assertFalse(warning.called, str(warning.call_args))
                self.assertEqual(len(dialog.job.commands()), 12)
                self.assertEqual({v.path for v, _ in dialog.job.commands()}, {v.path for v in videos[1:13]})
            finally:
                dialog.close()
                dialog.deleteLater()

    def test_nested_videos_are_counted_during_inspection(self):
        from PySide6.QtWidgets import QApplication
        from add_dub.gui_dialog import ConfigureDialog
        from add_dub.gui_model import Job, Settings
        from unittest.mock import Mock

        app = QApplication.instance() or QApplication([])
        tasks = Mock()
        args = parse_args(['--gui'])[0]
        with tempfile.TemporaryDirectory() as directory:
            nested = Path(directory) / 'saison' / 'bonus'
            nested.mkdir(parents=True)
            (Path(directory) / 'episode.mp4').touch()
            (nested / 'bonus.mkv').touch()
            dialog = ConfigureDialog(Job([directory], Settings.from_args(args), directory, recursive=False), tasks)
            try:
                dialog.show()
                app.processEvents()
                owner, work, done = tasks.run.call_args.args
                update = tasks.run.call_args.kwargs['progress']
                counts = []
                def report(value):
                    update(value)
                    counts.append(dialog.scan_progress.text())
                # La découverte parcourt les vrais sous-dossiers ; seule l’inspection média est simulée.
                with patch('add_dub.gui_dialog.inspect_video', side_effect=lambda video: video) as inspect:
                    videos = work(report)
                self.assertEqual(inspect.call_count, 2)
                self.assertEqual(counts, ['0/2', '1/2', '2/2'])
                done(videos, None)
                self.assertEqual(len(dialog.file_items), 2)
                self.assertTrue(dialog.job.preserve_tree)
                nested_video = next(v for v in dialog.job.videos if Path(v.path).name == 'bonus.mkv')
                self.assertEqual(Path(dialog.job.output_for(nested_video)),
                                 Path(directory) / Path(directory).name / 'saison' / 'bonus')
                folder = dialog.tree.topLevelItem(1)
                self.assertTrue(folder.isExpanded())
                opened = dialog.folder_icon(True).pixmap(28, 28).toImage()
                closed = dialog.folder_icon(False).pixmap(28, 28).toImage()
                self.assertNotEqual(opened, closed)
                self.assertEqual(folder.icon(0).pixmap(28, 28).toImage(), opened)
                folder.setExpanded(False)
                self.assertEqual(folder.icon(0).pixmap(28, 28).toImage(), closed)
                folder.setExpanded(True)
                self.assertEqual(folder.icon(0).pixmap(28, 28).toImage(), opened)
                self.assertEqual(dialog.scan_progress.text(), '2/2')
                self.assertTrue(dialog.job.recursive)
                # Replier un dossier partiellement coché doit conserver la sélection.
                from PySide6.QtCore import Qt
                from add_dub.gui_model import Track
                for video in dialog.job.videos:
                    video.audio = [Track('0', 'Audio')]
                    video.subtitles = [Track('srt', 'Sous-titres')]
                dialog.build_tree()
                folder = dialog.tree.topLevelItem(1)
                folder.setCheckState(0, Qt.CheckState.Unchecked)
                first = next(iter(dialog.file_items.values()))
                first.setCheckState(0, Qt.CheckState.Checked)
                self.assertEqual(folder.checkState(0), Qt.CheckState.PartiallyChecked)
                before = [v.selected for v in dialog.job.videos]
                self.assertEqual(sum(before), 1)
                for expanded in (False, True, False):
                    folder.setExpanded(expanded)
                    self.assertEqual(folder.checkState(0), Qt.CheckState.PartiallyChecked)
                    self.assertEqual([v.selected for v in dialog.job.videos], before)
            finally:
                dialog.close()
                dialog.deleteLater()

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
        tasks.run.side_effect = lambda owner, work, done, progress: done(work(progress), None)
        args = parse_args(['--gui'])[0]
        with tempfile.TemporaryDirectory() as directory:
            dialog = ConfigureDialog(Job([directory], Settings.from_args(args), directory), tasks)
            try:
                dialog.show()
                app.processEvents()
                self.assertTrue(dialog.isVisible())
                self.assertTrue(dialog.job.recursive)
                self.assertEqual(dialog.scan_progress.text(), '0/0')
                self.assertTrue(dialog.tree.isEnabled())
                self.assertFalse(dialog.add.isEnabled())
                self.assertTrue(dialog.resume.isChecked())
                dialog.overwrite.click()
                self.assertTrue(dialog.overwrite.isChecked())
                self.assertFalse(dialog.resume.isChecked())
                dialog.resume.click()
                self.assertTrue(dialog.resume.isChecked())
                self.assertFalse(dialog.overwrite.isChecked())
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
