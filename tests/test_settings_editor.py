import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from add_dub.config.editor import read_settings, save_settings, validate_settings
from add_dub.config.opts_loader import load_options


class SettingsFileTests(unittest.TestCase):
    def test_roundtrip_preserves_comments_unknowns_flags_and_quoted_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'options.conf'
            path.write_bytes(b'# custom\r\nbg = 1.0 d ; volume\r\nunknown = keep\r\n[logging]\r\nconsole_enable = true\r\n')
            values = read_settings(path)
            values.update(bg=2.0, input_dir='C:/My #folder;name', voice_id='Windows\\Voice')
            save_settings(values, path)
            result = path.read_bytes()
            self.assertIn(b'bg = 2.0 d  ; volume', result)
            self.assertIn(b'unknown = keep', result)
            self.assertIn(b'\r\n', result)
            with patch.dict(os.environ, {'ADD_DUB_OPTIONS': str(path)}):
                loaded = load_options()
            self.assertEqual(loaded['input_dir'].value, values['input_dir'])
            self.assertEqual(loaded['voice_id'].value, values['voice_id'])
            self.assertEqual(loaded['offset'].value, 0)
            self.assertTrue(loaded['bg'].display)

    def test_atomic_failure_and_validation_leave_original_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'options.conf'
            path.write_text('bg = 1.0\n', encoding='utf-8')
            before = path.read_bytes()
            values = read_settings(path)
            with patch('add_dub.config.editor.os.replace', side_effect=OSError('locked')):
                with self.assertRaises(OSError):
                    save_settings(values, path)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(list(Path(directory).glob('*.tmp')), [])
            values['bg'] = float('nan')
            with self.assertRaises(ValueError):
                save_settings(values, path)
            self.assertEqual(path.read_bytes(), before)

    def test_engine_and_codec_limits(self):
        values = read_settings(Path('__nonexistent_settings_test__'))
        values['min_rate_tts'] = .1
        self.assertIn('min_rate_tts', validate_settings(values))
        values['tts_engine'] = 'edge'
        self.assertNotIn('min_rate_tts', validate_settings(values))
        values['audio_bitrate'] = 333
        self.assertIn('audio_bitrate', validate_settings(values))
