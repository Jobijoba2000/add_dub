# add_dub/__main__.py
# 4 espaces d'indentation
import sys
from multiprocessing import freeze_support
from add_dub.cli.args import parse_args, want_interactive


def main(argv=None) -> int:
    freeze_support()
    args, _unknown = parse_args(argv or [])

    if want_interactive(args):
        # Comportement actuel : lance l'UI interactive
        from add_dub.cli.main import main as interactive_main
        return interactive_main()

    # Chemin batch pas encore implémenté
    print("Mode batch non implémenté. Utilisez --interactive (par défaut).")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
