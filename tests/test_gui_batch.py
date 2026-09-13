import unittest
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

from add_dub.gui.batch import command_text, launcher_command, open_terminal
from add_dub.gui.batch import write_batch_scripts, export_commands, batch_text


class BatchCommandTests(unittest.TestCase):
    def test_complete_folder_compacts_but_partial_selection_stays_exact(self):
        from add_dub.cli.args import parse_args
        from add_dub.gui.model import Job, Settings, Video, Track
        settings = Settings.from_args(parse_args(['--gui', '--tts-engine', 'gtts', '--voice', 'fr'])[0])
        settings.values['audio_index'] = '0'
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source'
            source.mkdir()
            videos = [Video(str(source / f'{i}.mkv'), str(source),
                            [Track('0', 'Audio')], [Track('srt', 'SRT')]) for i in range(3)]
            for video in videos:
                Path(video.path).touch()
            job = Job([str(source)], settings, str(Path(directory) / 'out'),
                      recursive=True, preserve_tree=True, videos=videos)
            commands = export_commands(job)
            self.assertEqual(len(commands), 1)
            self.assertEqual(commands[0][commands[0].index('--input') + 1], str(source))
            self.assertIn('--recursive', commands[0])
            self.assertIn('--preserve-tree', commands[0])
            self.assertIn('--skip-existing', commands[0])
            self.assertNotIn('cmd /d', batch_text(commands))
            videos[1].selected = False
            commands = export_commands(job)
            self.assertEqual([c[c.index('--input') + 1] for c in commands],
                             [videos[0].path, videos[2].path])
            videos[1].selected = True
            videos[1].audio = [Track('2', 'Audio')]
            # Les différences de pistes détectées ne sont pas des personnalisations.
            commands = export_commands(job)
            self.assertEqual(len(commands), 1)
            self.assertEqual(commands[0][commands[0].index('--audio-index') + 1],
                             settings.values['audio_index'])

    @unittest.skipUnless(os.name == 'nt', 'CMD Windows requis')
    def test_all_commands_run_without_stopping_at_pause(self):
        with tempfile.TemporaryDirectory() as directory:
            launcher = Path(directory) / 'launcher.cmd'
            launcher.write_text('@echo off\necho %~1>>"%~dp0seen.txt"\npause\nexit /b 0\n')
            script = write_batch_scripts([[str(launcher), 'first'], [str(launcher), 'second']], directory)
            result = subprocess.run(['cmd.exe', '/d', '/c', str(script)],
                                    capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertEqual((Path(directory) / 'seen.txt').read_text().splitlines(), ['first', 'second'])

    def test_batch_tab_includes_checked_videos_and_overrides(self):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from unittest.mock import Mock
        from copy import deepcopy
        from PySide6.QtWidgets import QApplication
        from add_dub.cli.args import parse_args
        from add_dub.gui.dialog import ConfigureDialog, COMMON
        from add_dub.gui.model import Job, Settings, Video, Track
        app = QApplication.instance() or QApplication([])
        settings = Settings.from_args(parse_args(['--gui', '--tts-engine', 'gtts', '--voice', 'fr'])[0])
        with tempfile.TemporaryDirectory() as directory:
            videos = [Video(str(Path(directory) / f'{i}.mkv'), audio=[Track('0', 'Audio')],
                            subtitles=[Track('srt', 'SRT')]) for i in range(3)]
            for video in videos:
                Path(video.path).touch()
            job = Job([directory], settings, directory, videos=videos)
            dialog = ConfigureDialog(job, Mock())
            try:
                dialog.build_tree()
                dialog.load_scope(COMMON, dialog.job.videos[0])
                custom = deepcopy(settings)
                custom.values['min_rate_tts'] = '1.5'
                dialog.job.overrides[videos[1].path] = custom
                from PySide6.QtCore import Qt
                dialog.file_items[videos[2].path].setCheckState(0, Qt.CheckState.Unchecked)
                self.assertEqual([dialog.editor.tabText(i) for i in range(dialog.editor.count())],
                                 ['Pistes', 'Voix', 'Traduction', 'Audio et temps', 'Essai'])
                dialog.show_batch()
                self.assertTrue(dialog.batch_page.isVisible())
                self.assertIn('2 vidéo(s)', dialog.batch_summary.text())
                dialog.refresh_batch()
                self.assertEqual(len(dialog.batch_command), 2)
                self.assertEqual([c[c.index('--input') + 1] for c in dialog.batch_command],
                                 [v.path for v in videos[:2]])
                second = dialog.batch_command[1]
                self.assertEqual(second[second.index('--min-rate-tts') + 1], '1.5')
                dialog.batch_page.reject()
                self.assertFalse(dialog.batch_page.isVisible())
            finally:
                dialog.close()
                dialog.deleteLater()

    def test_development_launcher_preserves_batch_options(self):
        options = ['--batch', '--input', 'C:/Vidéos/film & bonus.mkv',
                   '--min-rate-tts', '1.2', '--max-rate-tts', '1.8']
        with patch('add_dub.gui.batch.sys.frozen', False, create=True):
            command = launcher_command(['python.exe', '-u', '-m', 'add_dub', *options])
        self.assertTrue(command[0].endswith('start_add_dub.bat'))
        self.assertEqual(command[1:], options)
        self.assertIn('"C:/Vidéos/film & bonus.mkv"', command_text(command))

    def test_compiled_launcher_uses_current_executable(self):
        with patch('add_dub.gui.batch.sys.frozen', True, create=True), \
             patch('add_dub.gui.batch.sys.executable', 'C:/Mon app/add_dub.exe'):
            command = launcher_command(['old.exe', '--batch', '--overwrite'])
        self.assertEqual(command, ['C:/Mon app/add_dub.exe', '--batch', '--overwrite'])

    def test_terminal_passes_arguments_as_environment_values(self):
        command = ['C:/Mon app/add_dub.exe', '--batch', '--input', 'C:/film & 100%!.mkv']
        with patch('add_dub.gui.batch.subprocess.Popen') as launch:
            open_terminal(command)
        args, kwargs = launch.call_args
        self.assertIn('/k', args[0])
        self.assertNotIn(command[-1], args[0])
        self.assertEqual(kwargs['env']['ADD_DUB_BATCH_ARG_3'], command[-1])
        self.assertNotEqual(kwargs['creationflags'], 0)
