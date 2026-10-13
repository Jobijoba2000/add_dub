"""Frozen defaults and routing to a console that retains worker output."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from add_dub.launch import launcher_arguments, worker_executable, forward_console


class LauncherTests(unittest.TestCase):
    def test_frozen_defaults_and_explicit_modes(self):
        for name, mode in [('add_dub', '--gui'), ('add_dub_console', None), ('add_dub_player', '--player')]:
            with patch.object(sys, 'frozen', True, create=True), patch.object(sys, 'executable', name + '.exe'):
                self.assertEqual(launcher_arguments(['-i', 'film.mkv']),
                                 ([mode] if mode else []) + ['-i', 'film.mkv'])
                for explicit in ('--batch', '--interactive', '--gui', '--player', '--player-generate=request.json'):
                    self.assertEqual(launcher_arguments([explicit]), [explicit])

    def test_qt_workers_use_console_and_windowed_cli_is_forwarded(self):
        with tempfile.TemporaryDirectory() as directory:
            console = Path(directory) / 'add_dub_console.exe'
            console.touch()
            with patch.object(sys, 'frozen', True, create=True), \
                 patch.object(sys, 'executable', str(Path(directory) / 'add_dub_player.exe')):
                self.assertEqual(worker_executable(), str(console))
                with patch('add_dub.launch.subprocess.call', return_value=7) as run:
                    self.assertEqual(forward_console(['--interactive']), 7)
                    run.assert_called_once_with([str(console), '--interactive'])
                    self.assertIsNone(forward_console(['--player']))

    def test_sources_keep_console_default(self):
        with patch.object(sys, 'frozen', False, create=True):
            self.assertEqual(launcher_arguments([]), [])
            self.assertIsNone(forward_console(['--batch']))
            self.assertEqual(worker_executable(), sys.executable)
