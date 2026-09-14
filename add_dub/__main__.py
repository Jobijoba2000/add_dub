# add_dub/__main__.py
from __future__ import annotations

import sys
import os

from multiprocessing import freeze_support
try:
    import ctranslate2
except ImportError:
    pass

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

    if getattr(sys, "frozen", False):
        os.environ.setdefault("ADD_DUB_OPTIONS", os.path.join(os.path.dirname(sys.executable), "options.conf"))

    args, _unknown = parse_args(argv)

    if getattr(args, 'player_generate', None):
        from add_dub.player.core.generation import main as generate_main
        return generate_main(args.player_generate)

    if getattr(args, 'player', False):
        from add_dub.player.gui.run import main as player_main
        return player_main(args)

    if getattr(args, "gui", False):
        from add_dub.gui import main as gui_main
        return gui_main(args)

    # Actions utilitaires rapides
    if getattr(args, "list_voices", False):
        from add_dub.core.tts import list_available_voices
        for v in list_available_voices():
            print(v)
        return 0

    if want_interactive(args):
        from add_dub.cli.main import main as interactive_main
        return interactive_main()

    # Batch
    from add_dub.cli.batch import main as batch_main
    from add_dub.cli.batch_lifecycle import run
    return run(batch_main, args, argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
