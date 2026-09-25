"""Préserver les choix d'exécution TTS d'avant l'audit."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import wave

import numpy as np
from add_dub.core import tts_generate
from add_dub.core.options import DubOptions


class LegacyTtsExecutionTests(unittest.TestCase):
    def test_engine_executors_memory_assembly_and_progress(self):
        for engine in ('edge', 'gtts', 'onecore'):
            with self.subTest(engine=engine), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                source = root / 'source.srt'
                source.write_text('1\n00:00:00,000 --> 00:00:00,100\nBonjour\n', encoding='utf-8')
                segment = root / 'segment.wav'
                with wave.open(str(segment), 'wb') as stream:
                    stream.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
                    stream.writeframes(np.full(800, 1000, dtype='<i2').tobytes())
                executors = []
                def executor(**kwargs):
                    result = ThreadPoolExecutor(**kwargs)
                    result.shutdown = Mock(wraps=result.shutdown)
                    executors.append(result)
                    return result
                ui = Mock()
                with patch.object(tts_generate, 'cpu_count', return_value=24), \
                     patch.object(tts_generate, 'ProcessPoolExecutor', side_effect=executor) as processes, \
                     patch.object(tts_generate, 'ThreadPoolExecutor', side_effect=executor) as threads, \
                     patch.object(tts_generate, 'tts_worker', return_value=(0, str(segment), 0, 100)), \
                     patch.object(tts_generate.np, 'memmap', side_effect=AssertionError('assemblage disque interdit')), \
                     patch.object(tts_generate.np, 'zeros', wraps=np.zeros) as allocate:
                    output = root / 'tts.wav'
                    tts_generate.generate_dub_audio(str(source), str(output),
                        DubOptions(tts_engine=engine, voice_id='fr'), target_total_duration_ms=200, ui=ui)
                if engine == 'onecore':
                    processes.assert_called_once_with(max_workers=20)
                    threads.assert_called_once_with(max_workers=32)
                else:
                    processes.assert_not_called()
                    self.assertEqual([call.kwargs['max_workers'] for call in threads.call_args_list], [20, 32])
                executors[0].shutdown.assert_called_once_with(wait=False, cancel_futures=True)
                allocate.assert_called_once_with((1601, 1), dtype=np.int16)
                self.assertEqual([call.args[0] for call in ui.progress.call_args_list], [0, 100])
                with wave.open(str(output), 'rb') as stream:
                    samples = np.frombuffer(stream.readframes(stream.getnframes()), dtype='<i2')
                self.assertTrue(np.all(samples[:800] == 1000))
                self.assertTrue(np.all(samples[800:] == 0))
                self.assertFalse(segment.exists())

    def test_parallel_loader_preserves_trimming_and_stereo_conversion(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'source.wav'
            with wave.open(str(source), 'wb') as stream:
                stream.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
                stream.writeframes(np.arange(800, dtype='<i2').tobytes())
            result = tts_generate._load_segment_as_array(str(source), 8000, 2, 2, 25, 50)
            self.assertEqual(result.shape, (400, 2))
            np.testing.assert_array_equal(result[:, 0], np.arange(200, 600))
            np.testing.assert_array_equal(result[:, 0], result[:, 1])
