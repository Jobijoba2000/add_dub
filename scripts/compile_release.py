"""Compile the portable distribution, optionally creating a tagged Windows ZIP."""
import subprocess
import sys

from package_release import ROOT, archive, release_options, stage


def main(argv=None):
    args = release_options(argv, prog='compil.bat',
                           description='Compiler add_dub et préparer sa distribution Windows.')
    print('=== Compilation de add_dub avec PyInstaller ===', flush=True)
    commands = [
        [sys.executable, '-c', 'from PySide6 import QtWidgets; import PyInstaller, ctranslate2, sentencepiece'],
        [sys.executable, 'scripts/prepare_tools.py'],
        [sys.executable, 'scripts/build_app_icon.py'],
        [sys.executable, '-m', 'PyInstaller', '--clean', '--noconfirm', 'add_dub.spec'],
    ]
    try:
        for command in commands:
            subprocess.run(command, cwd=ROOT, check=True)
        distribution = stage()
        if args.archive:
            archive(distribution, tag=args.tag)
    except subprocess.CalledProcessError as exc:
        print('[ERREUR] Compilation ou préparation interrompue.', file=sys.stderr)
        return exc.returncode or 1
    except (OSError, ValueError) as exc:
        print(f'[ERREUR] {exc}', file=sys.stderr)
        return 1
    print('Compilation terminée dans dist/add_dub :', flush=True)
    print('  GUI : add_dub.exe\n  Console : add_dub_console.exe\n  Lecteur : add_dub_player.exe', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
