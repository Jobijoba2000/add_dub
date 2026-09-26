"""Durées des étapes et affichage console, sans moteur vocal distant."""
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import wave

from add_dub import logger
from add_dub.core import pipeline
from add_dub.core.options import DubOptions
from add_dub.core.ui import ConsoleUI
from add_dub.io import fs


class ConsoleTimingTests(unittest.TestCase):
    def test_progress_finishes_before_duration_on_separate_line(self):
        output = io.StringIO()
        @logger.log_time
        def step():
            ui = ConsoleUI()
            ui.progress(9)
            ui.progress(100)
        with patch('sys.stdout', output), patch.object(logger, 'is_console_enabled', return_value=True), \
             patch.object(logger.time, 'perf_counter', side_effect=[0, 4.21]):
            step()
        self.assertTrue(output.getvalue().endswith('Progress: 100.0%\n4.210 s\n'))

    def test_tts_and_ducking_each_print_their_duration(self):
        from add_dub.core import tts_generate, ducking
        with tempfile.TemporaryDirectory() as folder, patch.object(fs, 'TMP_DIR', folder):
            root = Path(folder)
            source = root / 'cue.srt'
            source.write_text('1\n00:00:00,000 --> 00:00:00,100\nBonjour\n', encoding='utf-8')
            segment = root / 'segment.wav'
            with wave.open(str(segment), 'wb') as wav:
                wav.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
                wav.writeframes(b'\0\0' * 800)
            output = io.StringIO()
            with patch('sys.stdout', output), patch.object(logger, 'is_console_enabled', return_value=True), \
                 patch.object(logger.time, 'perf_counter', side_effect=[0, 2, 2, 3]), \
                 patch.object(tts_generate, 'tts_worker', return_value=(0, str(segment), 0, 100)), \
                 patch.object(tts_generate, 'ProcessPoolExecutor', tts_generate.ThreadPoolExecutor):
                tts_generate.generate_dub_audio(str(source), str(root / 'tts.wav'), DubOptions(), ui=ConsoleUI())
                ducking.lower_audio_during_subtitles(root / 'tts.wav', [(0, .1, 'Bonjour')], root / 'duck.wav')
            self.assertTrue(output.getvalue().endswith('Progress: 100.0%\n2.000 s\n1.000 s\n'))

    def test_interactive_existing_output_does_not_prompt_or_force_translation_overwrite(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(fs, 'TMP_DIR', folder):
            (Path(folder) / 'film [dub-fr].mkv').touch()
            clock = [0]
            @logger.log_time
            def process(**kwargs):
                self.assertFalse(kwargs['opts'].overwrite)
                clock[0] += 3
                return 'finished'
            ui = Mock()
            ui.ask_yes_no.side_effect = AssertionError("Aucune question de remplacement")
            output = io.StringIO()
            with patch.object(pipeline, '_dub_code_from_voice', return_value='fr'), \
                 patch.object(pipeline, '_process_one_video', side_effect=process), \
                 patch('sys.stdout', output), patch.object(logger, 'is_console_enabled', return_value=True), \
                 patch.object(logger.time, 'perf_counter', side_effect=lambda: clock[0]):
                result = pipeline.process_one_video(input_video_path='film.mkv', input_video_name='film.mkv',
                    output_dir_path=folder, opts=DubOptions(), svcs=Mock(ui=ui))
            self.assertEqual(result, 'finished')
            self.assertEqual(output.getvalue(), '3.000 s\n')

    def test_batch_existing_output_still_requires_explicit_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / 'film [dub-fr].mkv').touch()
            ui = Mock()
            ui.ask_yes_no.return_value = False
            with patch.object(pipeline, '_dub_code_from_voice', return_value='fr'), \
                 patch.object(pipeline, '_process_one_video') as process:
                with self.assertRaises(FileExistsError):
                    pipeline.process_one_video(input_video_path='film.mkv', input_video_name='film.mkv',
                        output_dir_path=folder, opts=DubOptions(batch_mode=True), svcs=Mock(ui=ui))
                process.assert_not_called()
                ui.ask_yes_no.assert_not_called()
