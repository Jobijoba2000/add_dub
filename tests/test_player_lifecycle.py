"""La progression ne doit jamais interrompre le processus de préparation."""
import json
import os
from pathlib import Path
import sys
import time
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QProcess
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from add_dub.player.gui.generation_dialog import GenerationDialog


WORKER = '''
import json, sys, time, wave
from add_dub.progress import emit
r = json.load(open(sys.argv[1], encoding='utf-8'))
emit('stage', name='tts', text='Génération TTS')
emit('finalizing', name='tts')
# Longer than the erroneous 1500 ms kill timer previously in finalizing.
time.sleep(2)
emit('stage', name='ducking', text='Ducking audio')
time.sleep(.2)
for path in (r['output'], r['original_output']):
    with wave.open(path, 'wb') as wav:
        wav.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
        wav.writeframes(b'\\0\\0' * 800)
emit('result', path=r['output'], original_path=r['original_output'])
# A result must not kill the producer or unlock playback before exit.
time.sleep(.4)
'''


class GenerationLifecycleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_finalizing_survives_and_success_follows_process_exit(self):
        self.check_lifecycle(False)

    def test_automatic_restart_only_after_process_exit(self):
        self.check_lifecycle(True)

    def check_lifecycle(self, automatic):
        dialog = GenerationDialog({'video': 'lifecycle-test.mkv'}, auto_restart=automatic)
        request = json.loads(dialog.request_path.read_text(encoding='utf-8'))
        dialog.process.setProgram(sys.executable)
        dialog.process.setArguments(['-c', WORKER, str(dialog.request_path)])
        dialog.show()
        observed_result_before_exit = False
        try:
            deadline = time.monotonic() + 8
            while dialog.running and time.monotonic() < deadline:
                QTest.qWait(20)
                if dialog.output_path and dialog.process.state() != QProcess.ProcessState.NotRunning:
                    observed_result_before_exit = True
                    self.assertTrue(dialog.running)
                    self.assertFalse(dialog.continue_button.isVisible())
            self.assertFalse(dialog.running, dialog.log_tail)
            self.assertEqual(dialog.process.exitCode(), 0, dialog.label.text())
            self.assertTrue(observed_result_before_exit)
            if automatic:
                self.assertFalse(dialog.isVisible())
                self.assertEqual(dialog.choice, 'restart')
            else:
                self.assertTrue(dialog.restart_button.isVisible())
                self.assertTrue(dialog.continue_button.isVisible())
            self.assertFalse(dialog.button.isVisible())
            self.assertFalse(dialog.work.exists())
            if not automatic:
                dialog.continue_button.click()
                self.assertEqual(dialog.choice, 'continue')
        finally:
            if dialog.process.state() != QProcess.ProcessState.NotRunning:
                dialog.process.kill()
                dialog.process.waitForFinished(3000)
            dialog.close()
            for key in ('output', 'original_output'):
                Path(request[key]).unlink(missing_ok=True)


if __name__ == '__main__':
    unittest.main()
