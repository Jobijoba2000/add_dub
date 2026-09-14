"""Vérifie l'intégrité et la conservation des données lors de la préparation."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import prepare_tools
from add_dub.adapters.subtitle_edit import _subtitle_edit_language


class PrepareToolsTests(unittest.TestCase):

    def test_subtitle_edit_language_is_applied_and_kept_as_last_choice(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Path(directory) / 'Settings.xml'
            settings.write_text('<Settings><TesseractLastLanguage>fra</TesseractLastLanguage></Settings>',
                                encoding='utf-8')
            with _subtitle_edit_language(str(settings), 'eng'):
                self.assertIn('>eng<', settings.read_text(encoding='utf-8'))
            self.assertIn('>eng<', settings.read_text(encoding='utf-8'))
    def package(self, root):
        cache = root / '.cache'
        cache.mkdir()
        archive = cache / 'sample.zip'
        with zipfile.ZipFile(archive, 'w') as output:
            output.writestr('tool.exe', b'test executable')
            output.writestr('Settings.xml', b'default settings')
        return ('Test', 'sample', 'https://example.invalid/sample.zip',
                hashlib.sha256(archive.read_bytes()).hexdigest(), '.', ('tool.exe',))

    def test_fresh_subtitle_edit_install_replaces_archive_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / '.cache'
            cache.mkdir()
            archive = cache / 'subtitle.zip'
            with zipfile.ZipFile(archive, 'w') as output:
                output.writestr('SubtitleEdit.exe', b'executable')
                output.writestr('Settings.xml', '<TesseractLastLanguage>archive</TesseractLastLanguage>')
            source = Path(prepare_tools.__file__).parent / 'assets/subtitle_edit/Settings.xml'
            destination = root / 'tools/subtitle_edit/Settings.xml'
            package = ('Subtitle Edit', 'subtitle_edit', 'https://example.invalid/subtitle.zip',
                       hashlib.sha256(archive.read_bytes()).hexdigest(), '.', ('SubtitleEdit.exe',))
            prepare_tools.prepare_package(root, package)
            self.assertEqual(destination.read_bytes(), source.read_bytes())

    def test_cached_install_and_second_run_do_not_download(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = self.package(root)
            with patch.object(prepare_tools, 'download', side_effect=AssertionError('network')):
                prepare_tools.prepare_package(root, package)
                prepare_tools.prepare_package(root, package)
            self.assertEqual((root / 'tools/sample/tool.exe').read_bytes(), b'test executable')

    def test_repair_preserves_user_settings_and_models(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = self.package(root)
            target = root / 'tools/sample'
            target.mkdir(parents=True)
            (target / 'Settings.xml').write_text('user settings')
            (target / 'fra.traineddata').write_bytes(b'user model')
            prepare_tools.prepare_package(root, package)
            self.assertEqual((target / 'Settings.xml').read_text(), 'user settings')
            self.assertEqual((target / 'fra.traineddata').read_bytes(), b'user model')

    def test_wrong_download_hash_never_installs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = self.package(root)
            (root / '.cache/sample.zip').write_bytes(b'corrupted cache')
            with patch.object(prepare_tools, 'download',
                              side_effect=lambda url, path: path.write_bytes(b'bad download')):
                with self.assertRaisesRegex(RuntimeError, 'empreinte'):
                    prepare_tools.prepare_package(root, package)
            self.assertFalse((root / 'tools/sample').exists())


if __name__ == '__main__':
    unittest.main()
