"""Révisions explicites ; aucun téléchargement sur une branche flottante."""
import json
from pathlib import Path
import sys


def revisions():
    from add_dub.io.fs import ROOT
    path = Path(ROOT) / 'models.lock.json'
    if not path.exists() and getattr(sys, 'frozen', False):
        path = Path(sys._MEIPASS) / 'models.lock.json'
    return json.loads(path.read_text(encoding='utf-8'))


def snapshot(repo_id, directory):
    from add_dub.io.work import is_offline
    if is_offline():
        raise RuntimeError('Téléchargement interdit en mode hors ligne.')
    from huggingface_hub import snapshot_download
    revision = revisions().get(repo_id)
    if not revision:
        raise ValueError(f'Modèle non épinglé : {repo_id}. Ajoutez sa révision à models.lock.json.')
    return snapshot_download(repo_id=repo_id, revision=revision, local_dir=directory,
                             allow_patterns=['*.bin', '*.json', '*.spm', '*.model', 'LICENSE*', 'README*'],
                             etag_timeout=20, max_workers=2)
