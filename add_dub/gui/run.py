"""Fichiers appartenant à une seule vidéo GUI ; nettoyage sans toucher aux autres."""
import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path


def partition_existing(pending):
    """Vérifie les sorties en groupe, sans démarrer Python pour chaque vidéo."""
    remaining, skipped = [], []
    languages, directories = {}, {}
    for entry in pending:
        _, video, command = entry
        if '--skip-existing' not in command or '--overwrite' in command or '--dry-run' in command:
            remaining.append(entry)
            continue
        try:
            voice = command[command.index('--voice') + 1]
            directory = Path(command[command.index('--output-dir') + 1])
        except (ValueError, IndexError):
            remaining.append(entry)
            continue
        if voice not in languages:
            # Même convention que le pipeline, y compris les voix OneCore.
            from add_dub.core.pipeline import _dub_code_from_voice
            languages[voice] = _dub_code_from_voice(voice)
        key = os.path.normcase(os.path.abspath(directory))
        if key not in directories:
            try:
                with os.scandir(directory) as files:
                    directories[key] = {os.path.normcase(f.name) for f in files if f.is_file()}
            except OSError:
                directories[key] = set()
        expected = os.path.normcase(f'{Path(video.path).stem} [dub-{languages[voice]}].mkv')
        (skipped if expected in directories[key] else remaining).append(entry)
    return remaining, skipped


class VideoRunFiles:
    def __init__(self, temp_root, output_dir):
        self.root = Path(temp_root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.work = Path(tempfile.mkdtemp(prefix='gui-video-', dir=self.root)).resolve()
        self.output_dir = Path(output_dir).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.partial = self.output_dir / f'.add_dub-{uuid.uuid4().hex}.partial.mkv'

    def publish(self):
        manifest = self.work / 'result.json'
        if not manifest.exists():
            if self.partial.exists():
                raise RuntimeError('Mixage incomplet : la sortie ne sera pas publiée.')
            return  # Sortie existante ignorée ou vérification seule.
        destination = Path(json.loads(manifest.read_text(encoding='utf-8'))['destination']).resolve()
        if destination.parent != self.output_dir or destination.suffix.lower() != '.mkv':
            raise RuntimeError('Destination inattendue pour la vidéo terminée.')
        os.replace(self.partial, destination)

    def cleanup(self):
        if self.work.parent != self.root or not self.work.name.startswith('gui-video-'):
            raise RuntimeError('Dossier temporaire inattendu : nettoyage refusé.')
        if self.partial.parent != self.output_dir or not self.partial.name.startswith('.add_dub-'):
            raise RuntimeError('Sortie temporaire inattendue : nettoyage refusé.')
        self.partial.unlink(missing_ok=True)
        if self.work.exists():
            shutil.rmtree(self.work)
