# add_dub/__main__.py
from __future__ import annotations

import sys
from multiprocessing import freeze_support

from add_dub.cli.args import parse_args, want_interactive


def main(argv=None) -> int:
    freeze_support()
    args, _unknown = parse_args(argv or [])

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
    return batch_main(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
