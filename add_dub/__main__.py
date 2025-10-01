# add_dub/__main__.py
import sys
from multiprocessing import freeze_support
from add_dub.cli import main

if __name__ == "__main__":
    freeze_support()
    sys.exit(main())
