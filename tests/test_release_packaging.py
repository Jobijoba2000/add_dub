"""Release options must not compile on invalid input or leak personal files."""
import contextlib
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

with patch.object(sys, 'path', [str(Path(__file__).resolve().parents[1] / 'scripts'), *sys.path]):
    import compile_release
    import package_release


class ReleaseOptionsTests(unittest.TestCase):
    def test_default_and_prerelease_archive_names(self):
        self.assertEqual(package_release.release_options(['--zip']).tag,
                         f'v{package_release.__version__}')
        self.assertEqual(package_release.release_options(['--zip', '--tag', '2.0.0-rc1']).tag,
                         'v2.0.0-rc1')
        self.assertEqual(package_release.release_options(['--archive', '--tag', 'v2.0.0']).tag,
                         'v2.0.0')

    def test_help_and_invalid_options_do_not_start_compilation(self):
        with patch.object(compile_release.subprocess, 'run') as run:
            for args in (['--help'], ['--tag', 'v2.0.0'],
                         ['--zip', '--tag', '../outside'], ['--zip', '--tag', 'C:\\outside'],
                         ['--zip', '--tag', 'bad tag'], ['--zip', '--tag'], ['--unknown']):
                with self.subTest(args=args), contextlib.redirect_stdout(io.StringIO()), \
                        contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as error:
                        compile_release.main(args)
                    self.assertEqual(error.exception.code, 0 if args == ['--help'] else 2)
            run.assert_not_called()

    def test_compilation_archives_only_when_requested(self):
        with patch.object(compile_release.subprocess, 'run'), \
                patch.object(compile_release, 'stage', return_value=Path('dist/add_dub')), \
                patch.object(compile_release, 'archive') as archive, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(compile_release.main([]), 0)
            archive.assert_not_called()
            self.assertEqual(compile_release.main(['--zip', '--tag', 'v2.0.0-rc1']), 0)
            archive.assert_called_once_with(Path('dist/add_dub'), tag='v2.0.0-rc1')

    def test_failed_compilation_does_not_package_old_executables(self):
        with patch.object(compile_release.subprocess, 'run',
                          side_effect=subprocess.CalledProcessError(7, ['build'])), \
                patch.object(compile_release, 'stage') as stage, \
                patch.object(compile_release, 'archive') as archive, \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(compile_release.main(['--zip']), 7)
            stage.assert_not_called()
            archive.assert_not_called()

    def test_tagged_zip_keeps_sample_and_docs_excludes_personal_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            distribution = root / 'dist' / 'add_dub'
            files = {'add_dub.exe': b'launcher', 'input/extrait.mkv': b'sample',
                     'docs/documentation.html': b'online documentation',
                     'input/personal.mkv': b'personal', 'output/private.mkv': b'private',
                     'options.conf': b'preferences', '.cache/model': b'cache'}
            for name, content in files.items():
                path = distribution / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            with patch.object(package_release, 'ROOT', root), contextlib.redirect_stdout(io.StringIO()):
                target = package_release.archive(distribution, tag='v2.0.0-rc1')
            self.assertEqual(target.name, 'add_dub_v2.0.0-rc1_win64.zip')
            with zipfile.ZipFile(target) as archive:
                self.assertEqual(set(archive.namelist()),
                                 {'add_dub/add_dub.exe', 'add_dub/input/extrait.mkv',
                                  'add_dub/docs/documentation.html'})
                self.assertIsNone(archive.testzip())
            self.assertEqual(list(target.parent.glob('*.zip')), [target])


if __name__ == '__main__':
    unittest.main()
