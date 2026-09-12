import json
import tempfile
import unittest
from pathlib import Path
from add_dub.gui.run import VideoRunFiles, partition_existing


class RunFilesTests(unittest.TestCase):
    def test_42_existing_outputs_leave_58_to_process(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        import os
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        from add_dub.gui.application import Application
        from add_dub.cli.args import parse_args
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory:
            videos = [SimpleNamespace(path=f'episode{i}.mkv') for i in range(100)]
            for i in range(42):
                (Path(directory) / f'episode{i} [dub-fr].mkv').touch()
            command = ['python', '--batch', '--skip-existing', '--voice', 'fr', '--output-dir', directory]
            job = SimpleNamespace(selected=videos, completed=set(), status='En attente',
                                  output_for=lambda v: directory,
                                  commands=lambda: [(v, command) for v in videos])
            with patch('add_dub.gui.application.fs.ensure_base_dirs'):
                window = Application(parse_args(['--gui'])[0])
            window.jobs = [job]
            try:
                with patch('add_dub.core.pipeline._dub_code_from_voice', return_value='fr') as language, patch.object(window, 'next_file'):
                    window.start()
                language.assert_called_once_with('fr')
                self.assertEqual(len(window.pending), 58)
                self.assertEqual(len(job.completed), 42)
                self.assertEqual(window.progress.value(), 0)
                self.assertEqual(window.durations, [])
                self.assertIn('Restant estimé : —', window.time_label.text())
                window.position = 10
                window.update_totals()
                self.assertGreater(window.progress.value(), 0)
                window.request_stop()
                self.assertEqual(window.progress.value(), 0)
                self.assertEqual(len(job.completed), 42)
                with patch('add_dub.core.pipeline._dub_code_from_voice', return_value='fr'), patch.object(window, 'next_file'):
                    window.start()
                self.assertEqual(len(window.pending), 58)
                self.assertEqual(window.progress.value(), 0)
            finally:
                window.running = False
                window.close()
                window.deleteLater()

    def test_preflight_respects_overwrite_and_dry_run(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / 'video [dub-fr].mkv').touch()
            video = SimpleNamespace(path='video.mkv')
            for extra in (['--overwrite'], ['--dry-run']):
                pending = [(0, video, ['python', '--skip-existing', '--voice', 'fr', '--output-dir', directory] + extra)]
                remaining, skipped = partition_existing(pending)
                self.assertEqual(remaining, pending)
                self.assertEqual(skipped, [])

    def test_real_stop_kills_batch_and_cleans_partial_files(self):
        import os
        import sys
        import time
        from types import SimpleNamespace
        from unittest.mock import patch
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        from add_dub.gui.application import Application
        from add_dub.cli.args import parse_args
        app = QApplication.instance() or QApplication([])
        script = '''import os, subprocess, sys, time
from pathlib import Path
from add_dub.io import fs
fs.ensure_base_dirs()
assert fs.TMP_DIR == os.environ['ADD_DUB_GUI_WORK_TMP']
child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
Path(fs.TMP_DIR, 'segment.wav').write_text('tmp')
Path(os.environ['ADD_DUB_GUI_PARTIAL_OUTPUT']).write_text('unfinished')
Path(fs.TMP_DIR, 'ready').write_text(str(child.pid))
time.sleep(60)
'''
        with tempfile.TemporaryDirectory() as directory:
            with patch('add_dub.gui.application.fs.ensure_base_dirs'):
                window = Application(parse_args(['--gui'])[0])
            video = SimpleNamespace(path='simulation.mkv')
            window.jobs = [SimpleNamespace(selected=[video], status='En attente', completed=set(),
                                           output_for=lambda v: directory,
                                           commands=lambda: [(video, [sys.executable, '-c', script])])]
            try:
                window.start()
                files = window.run_files
                deadline = time.monotonic() + 10
                while not (files.work / 'ready').exists() and time.monotonic() < deadline:
                    app.processEvents()
                    time.sleep(.01)
                self.assertTrue((files.work / 'ready').exists())
                window.request_stop()
                deadline = time.monotonic() + 10
                while window.running and time.monotonic() < deadline:
                    app.processEvents()
                    time.sleep(.01)
                self.assertFalse(window.running, window.status.text())
                self.assertFalse(files.work.exists())
                self.assertFalse(files.partial.exists())
                self.assertEqual(window.position, 0)
                self.assertFalse(window.jobs[0].completed)
                self.assertEqual(window.progress.value(), 0)
                self.assertEqual(window.queue.topLevelItem(0).text(2), 'En attente')
            finally:
                window.process.kill()
                window.process.waitForFinished(1000)
                window.running = False
                window.close()
                window.deleteLater()

    def test_cancel_removes_only_owned_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            unrelated = root / 'keep.wav'
            unrelated.write_text('keep')
            run = VideoRunFiles(root, root / 'output')
            existing = run.output_dir / 'film.mkv'
            existing.write_text('previous successful output')
            (run.work / 'segment.wav').write_text('temporary')
            run.partial.write_text('incomplete mux')
            run.cleanup()
            self.assertFalse(run.work.exists())
            self.assertFalse(run.partial.exists())
            self.assertEqual(existing.read_text(), 'previous successful output')
            self.assertTrue(unrelated.exists())

    def test_only_success_publishes_mux(self):
        with tempfile.TemporaryDirectory() as directory:
            run = VideoRunFiles(directory, Path(directory) / 'output')
            destination = run.output_dir / 'film.mkv'
            run.partial.write_text('complete')
            (run.work / 'result.json').write_text(json.dumps({'destination': str(destination)}))
            run.publish()
            run.cleanup()
            self.assertEqual(destination.read_text(), 'complete')

    def test_manifest_cannot_publish_outside_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            run = VideoRunFiles(directory, Path(directory) / 'output')
            run.partial.write_text('complete')
            (run.work / 'result.json').write_text(json.dumps({'destination': str(Path(directory) / 'other.mkv')}))
            with self.assertRaises(RuntimeError):
                run.publish()
            run.cleanup()


if __name__ == '__main__':
    unittest.main()
