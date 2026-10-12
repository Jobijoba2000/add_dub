"""Les réglages globaux sont appliqués au moteur et au journal sans redémarrage."""
import importlib
import logging
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class SettingsRuntimeTests(unittest.TestCase):
    def test_batch_uses_reuse_and_original_language_from_config(self):
        from add_dub.cli.args import parse_args
        from add_dub.cli.batch import _make_options
        from add_dub.config.effective import effective_values

        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'options.conf'
            config.write_text('reuse_translated_subs = false d\n'
                              'orig_audio_lang = "Version originale"\n'
                              'ask_test_before_cleanup = true\n', encoding='utf-8')
            with patch.dict(os.environ, {'ADD_DUB_OPTIONS': str(config)}), patch(
                    'add_dub.cli.batch.resolve_voice_with_fallbacks', return_value={'id': 'fr'}):
                self.assertFalse(effective_values()['reuse_translated_subs'])
                args = parse_args(['--batch', '--tts-engine', 'gtts', '--voice', 'fr'])[0]
                opts = _make_options(args)
                self.assertFalse(opts.reuse_translated_subs)
                self.assertFalse(opts.ask_reuse_subs)
                self.assertFalse(opts.ask_test_before_cleanup)
                self.assertEqual(opts.orig_audio_lang, 'Version originale')


class LoggingSettingsTests(unittest.TestCase):
    def setUp(self):
        self.runtime = importlib.import_module('add_dub.logger')
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.config = self.root / 'options.conf'
        self.config.write_text('', encoding='utf-8')
        self.log = logging.Logger('settings-runtime-test', logging.DEBUG)
        self.log.propagate = False
        for context in (
                patch.dict(os.environ, {'ADD_DUB_OPTIONS': str(self.config)}),
                patch.object(self.runtime, 'logger', self.log),
                patch.object(self.runtime, '_file_handler', None),
                patch.object(self.runtime, '_console_handler', None),
                patch.object(self.runtime, '_logging_base_dir', return_value=str(self.root))):
            context.start()
            self.addCleanup(context.stop)
        self.addCleanup(self.close_handlers)

    def close_handlers(self):
        for handler in list(self.log.handlers):
            self.log.removeHandler(handler)
            handler.close()

    def write(self, text):
        self.config.write_text('[logging]\n' + text, encoding='utf-8')

    def test_defaults_and_live_level_change_reuse_handlers(self):
        self.runtime.reload_config()
        file_handler = self.runtime._file_handler
        console_handler = self.runtime._console_handler
        self.assertEqual(file_handler.level, logging.DEBUG)
        self.assertEqual(Path(file_handler.baseFilename), self.root / 'logs' / 'add_dub.log')
        self.write('console_level = ERROR\nfile_level = WARNING\n')
        self.runtime.reload_config()
        self.assertIs(self.runtime._file_handler, file_handler)
        self.assertIs(self.runtime._console_handler, console_handler)
        self.assertEqual(file_handler.level, logging.WARNING)
        self.assertEqual(console_handler.level, logging.ERROR)
        self.log.info('not in journal')
        self.log.warning('in journal')
        contents = Path(file_handler.baseFilename).read_text(encoding='utf-8')
        self.assertNotIn('not in journal', contents)
        self.assertIn('in journal', contents)
        self.assertEqual(len(self.log.handlers), 2)

    def test_switch_file_then_disable_handlers_closes_them(self):
        self.runtime.reload_config()
        first = self.runtime._file_handler
        self.write('console_enable = false\ndir = "custom logs"\nfile_name = "session.log"\n')
        self.runtime.reload_config()
        second = self.runtime._file_handler
        self.assertIsNot(second, first)
        self.assertIsNone(first.stream)
        self.assertIsNone(self.runtime._console_handler)
        self.assertEqual(Path(second.baseFilename), self.root / 'custom logs' / 'session.log')
        self.log.debug('new file')
        self.assertIn('new file', Path(second.baseFilename).read_text(encoding='utf-8'))
        self.write('console_enable = false\nfile_enable = false\n')
        self.runtime.reload_config()
        self.assertIsNone(second.stream)
        self.assertIsNone(self.runtime._file_handler)
        self.assertEqual(self.log.handlers, [self.runtime._silence_handler])
        with patch('logging.lastResort') as fallback:
            self.log.error('both outputs disabled')
            fallback.handle.assert_not_called()

    def test_failed_new_file_keeps_previous_logging_live(self):
        self.runtime.reload_config()
        first = self.runtime._file_handler
        console = self.runtime._console_handler
        blocker = self.root / 'not-a-directory'
        blocker.write_text('existing file', encoding='utf-8')
        self.write('console_enable = false\ndir = "not-a-directory"\n')
        with self.assertRaises(OSError):
            self.runtime.reload_config()
        self.assertIs(self.runtime._file_handler, first)
        self.assertIs(self.runtime._console_handler, console)
        self.assertEqual(len(self.log.handlers), 2)
        self.log.debug('still active')
        self.assertIn('still active', Path(first.baseFilename).read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
