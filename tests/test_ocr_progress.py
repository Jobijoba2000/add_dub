import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from add_dub.adapters.subtitle_edit import _run_ocr


class OcrProgressTests(unittest.TestCase):
    def test_fragmented_cr_updates_arrive_before_process_finishes(self):
        # The child only finishes after the parent receives its 42% update.
        # This detects buffering until newline/EOF, not just correct parsing.
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / 'received'
            script = (
                "import sys,time,pathlib\n"
                "sys.stdout.write('\\rOCR : 4');sys.stdout.flush()\n"
                "time.sleep(.1)\n"
                "sys.stdout.write('2%');sys.stdout.flush()\n"
                "marker=pathlib.Path(sys.argv[1])\n"
                "deadline=time.monotonic()+5\n"
                "while not marker.exists() and time.monotonic()<deadline: time.sleep(.02)\n"
                "assert marker.exists(), 'Progress was buffered until exit'\n"
                "sys.stdout.write('\\rOCR : 45,5%\\rOCR : 100%')\n"
            )
            values = []

            def report(kind, **data):
                values.append(data['value'])
                if data['value'] == 42:
                    marker.touch()

            with patch('add_dub.progress.emit', side_effect=report), contextlib.redirect_stdout(io.StringIO()):
                _run_ocr([sys.executable, '-c', script, str(marker)], timeout=10)
            self.assertEqual(values, [42, 45.5, 100])

    def test_silent_process_times_out_and_nonzero_exit_fails(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            _run_ocr([sys.executable, '-c', 'import time;time.sleep(20)'], timeout=.3)
        with self.assertRaises(subprocess.CalledProcessError):
            _run_ocr([sys.executable, '-c', 'raise SystemExit(3)'])

    def test_ducking_reports_progress_even_without_attenuated_intervals(self):
        from add_dub.core.ducking import lower_audio_during_subtitles
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory) / 'source.wav', Path(directory) / 'target.wav'
            with wave.open(str(source), 'wb') as stream:
                stream.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
                stream.writeframes(b'\0\0' * 200000)
            values = []
            lower_audio_during_subtitles(source, [], target, progress_cb=values.append)
            self.assertEqual(values[0], 0)
            self.assertEqual(values[-1], 100)
            self.assertTrue(any(0 < value < 100 for value in values))
            self.assertEqual(values, sorted(values))
            self.assertEqual(source.read_bytes(), target.read_bytes())
