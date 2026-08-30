# add_dub/__main__.py
from __future__ import annotations

import sys

from multiprocessing import freeze_support
import ctranslate2

if sys.platform == "win32":
    import ctypes
    try:
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        ctypes.windll.kernel32.SetConsoleCP(65001)
    except Exception:
        pass
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from add_dub.cli.args import parse_args, want_interactive


def main(argv=None) -> int:
    freeze_support()

    if argv is None:
        argv = sys.argv[1:]

    args, _unknown = parse_args(argv)

    # Actions utilitaires rapides
    if getattr(args, "list_voices", False):
        from add_dub.core.tts import list_available_voices
        for v in list_available_voices():
            print(v)
        return 0

    if getattr(args, "gui", False):
        from add_dub.gui.qt_app import main as gui_main
        return gui_main()

    if want_interactive(args):
        from add_dub.cli.main import main as interactive_main
        return interactive_main()

    # Batch
    from add_dub.cli.batch import main as batch_main
    return batch_main(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
