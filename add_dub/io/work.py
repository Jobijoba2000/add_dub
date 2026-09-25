"""Contexte local d'un travail ; aucune mutation globale de dossiers."""
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
import os
import tempfile

CURRENT = ContextVar('add_dub_work', default=None)
OFFLINE = ContextVar('add_dub_offline', default=False)


@contextmanager
def work_directory(root=None):
    from . import fs
    root = root or fs.TMP_DIR
    Path(root).mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='dub-job-', dir=root) as directory:
        token = CURRENT.set(directory)
        try:
            yield directory
        finally:
            CURRENT.reset(token)


def publish(source, destination, overwrite=False):
    """Publication sur le même volume, sans écrasement implicite ni race."""
    if overwrite:
        os.replace(source, destination)
    elif os.name == 'nt':
        os.rename(source, destination)  # Windows refuse une destination existante.
    else:
        os.link(source, destination)
        os.unlink(source)


def is_offline():
    return OFFLINE.get() or os.environ.get('ADD_DUB_OFFLINE') == '1'
