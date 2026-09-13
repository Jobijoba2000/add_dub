"""Modèles de lots et commandes du moteur, indépendants de Qt."""
from __future__ import annotations
import os
import sys
import math
import json
import subprocess
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from add_dub.io import fs

# Valeurs sérialisées explicitement : aucune commande shell construite.
FIELDS = (
    ('tts_engine', 'Moteur vocal', ('onecore', 'edge', 'gtts')),
    ('voice', 'Voix (identifiant ; vide = automatique)', None),
    ('audio_index', 'Piste audio (index FFmpeg ; vide = première)', None),
    ('sub', 'Sous-titres (auto, srt ou mkv:index)', None),
    ('translation_engine', 'Moteur de traduction', ('ctranslate2', 'google')),
    ('translate_to', 'Langue cible (fr, en, es…)', None),
    ('translate_from', 'Langue source (vide = automatique)', None),
    ('audio_codec', 'Codec audio', ('ac3', 'aac', 'mp3', 'flac', 'pcm_s16le')),
    ('audio_bitrate', 'Débit audio (kbit/s)', None),
    ('ducking_db', 'Atténuation du fond (dB)', None),
    ('bg_mix', 'Volume original', None),
    ('tts_mix', 'Volume des voix', None),
    ('offset_ms', 'Décalage des sous-titres (ms)', None),
    ('offset_video_ms', 'Décalage vidéo (ms)', None),
    ('min_rate_tts', 'Vitesse minimale TTS', None),
    ('max_rate_tts', 'Vitesse maximale TTS', None),
    ('limit_duration_sec', 'Extrait de test (secondes ; vide = entier)', None),
)
INTS = {'audio_index', 'audio_bitrate', 'offset_ms', 'offset_video_ms', 'limit_duration_sec'}
FLOATS = {'ducking_db', 'bg_mix', 'tts_mix', 'min_rate_tts', 'max_rate_tts'}
BOOLS = ('translate', 'recursive', 'preserve_tree', 'overwrite', 'skip_existing', 'dry_run')


def batch_command(values, flags, paths, output):
    """Valide le formulaire et crée les arguments, en sources comme en EXE."""
    if not paths:
        raise ValueError('Ajoutez au moins une vidéo ou un dossier.')
    for path in paths:
        if not os.path.exists(path):
            raise ValueError(f'Chemin introuvable : {path}')
    if not output.strip():
        raise ValueError('Choisissez un dossier de sortie.')
    numbers = {}
    for name in INTS | FLOATS:
        raw = values[name].strip()
        if not raw and name in {'audio_index', 'limit_duration_sec'}:
            continue
        try:
            numbers[name] = int(raw) if name in INTS else float(raw)
            if not math.isfinite(numbers[name]):
                raise ValueError()
        except ValueError:
            label = next(label for key, label, _ in FIELDS if key == name)
            raise ValueError(f'Valeur numérique invalide : {label}') from None
    for name in ('audio_bitrate', 'min_rate_tts', 'max_rate_tts', 'limit_duration_sec'):
        if name in numbers and numbers[name] <= 0:
            raise ValueError(f'{name} doit être strictement positif.')
    if any(numbers.get(n, 0) < 0 for n in ('audio_index', 'bg_mix', 'tts_mix')):
        raise ValueError('Les index et les volumes doivent être positifs ou nuls.')
    if numbers['min_rate_tts'] > numbers['max_rate_tts']:
        raise ValueError('La vitesse minimale dépasse la vitesse maximale.')
    import re
    if not re.fullmatch(r'auto|srt|(?:mkv|stream)(?::\d+)?', values['sub'].strip()):
        raise ValueError('Sous-titres : utilisez auto, srt ou mkv:0, mkv:1…')
    if flags['translate']:
        for name in ('translate_to', 'translate_from'):
            raw = values[name].strip()
            if (raw or name == 'translate_to') and not re.fullmatch('[a-zA-Z]{2}', raw):
                raise ValueError('Utilisez un code langue de deux lettres (fr, en…).')
    if flags['overwrite'] and flags['skip_existing']:
        raise ValueError('Choisissez soit remplacer, soit ignorer les sorties existantes.')
    command = [sys.executable] if getattr(sys, 'frozen', False) else [sys.executable, '-u', '-m', 'add_dub']
    command += ['--batch', '--input', *paths, '--output-dir', os.path.abspath(output)]
    for name, _, _ in FIELDS:
        raw = values[name].strip()
        if raw:
            command += ['--' + name.replace('_', '-'), raw]
    command += ['--translate' if flags['translate'] else '--no-translate']
    for name in BOOLS[1:]:
        if flags[name]:
            command.append('--' + name.replace('_', '-'))
    return command


VIDEO_EXTENSIONS = {'.mkv', '.mp4', '.avi', '.mov'}


@dataclass
class Track:
    value: str
    label: str
    language: str = ''
    title: str = ''
    kind: str = ''
    ordinal: int = 0


@dataclass
class Video:
    path: str
    root: str = ''
    audio: list[Track] = field(default_factory=list)
    subtitles: list[Track] = field(default_factory=list)
    error: str = ''
    selected: bool = True

    @property
    def eligible(self):
        return bool(self.audio and self.subtitles and not self.error)

    @property
    def reason(self):
        return self.error or ('Aucun sous-titre détecté' if not self.subtitles else
                              'Aucune piste audio' if not self.audio else 'Prêt')


@dataclass
class Settings:
    values: dict
    translate: bool = False
    audio: Track | None = None
    subtitle: Track | None = None

    @classmethod
    def from_args(cls, args):
        return cls({key: '' if getattr(args, key, None) is None else str(getattr(args, key))
                    for key, _, _ in FIELDS}, args.translate)


def match_track(reference, tracks):
    if not tracks:
        return None
    if reference:
        # Langue et titre priment sur l'index physique, qui peut changer entre épisodes.
        candidates = [t for t in tracks if t.kind == reference.kind]
        if reference.language or reference.title:
            exact = [t for t in candidates if (not reference.language or t.language == reference.language)
                     and (not reference.title or t.title == reference.title)]
            if exact:
                return exact[0]
            language = [t for t in candidates if reference.language and t.language == reference.language]
            if language:
                return language[0]
        same_position = [t for t in candidates if t.ordinal == reference.ordinal]
        if same_position:
            return same_position[0]
        if candidates:
            return candidates[0]
    return tracks[0]


def adapt_settings(settings, video):
    result = deepcopy(settings)
    for key, attr, tracks in (('audio_index', 'audio', video.audio), ('sub', 'subtitle', video.subtitles)):
        ref = getattr(result, attr)
        chosen = match_track(ref, tracks) if ref else next((t for t in tracks if t.value == result.values.get(key)), None)
        chosen = chosen or (tracks[0] if tracks else None)
        setattr(result, attr, chosen)
        result.values[key] = chosen.value if chosen else ''
    return result


@dataclass
class Job:
    sources: list[str]
    common: Settings
    output: str
    recursive: bool = False
    preserve_tree: bool = False
    resume: bool = True
    dry_run: bool = False
    videos: list[Video] = field(default_factory=list)
    overrides: dict[str, Settings] = field(default_factory=dict)
    folder_configs: dict[str, Settings] = field(default_factory=dict)
    config_numbers: dict[str, int] = field(default_factory=dict)
    next_config_number: int = 1
    status: str = 'En attente'
    completed: set[str] = field(default_factory=set)

    @property
    def selected(self):
        return [v for v in self.videos if v.selected and v.eligible]

    def folder_scope(self, path):
        path = Path(os.path.abspath(path))
        matches = [folder for folder in self.folder_configs
                   if path == Path(os.path.abspath(folder)) or Path(os.path.abspath(folder)) in path.parents]
        return max(matches, key=lambda folder: len(Path(folder).parts), default=None)

    def settings_for(self, video):
        folder = self.folder_scope(video.path)
        inherited = self.folder_configs[folder] if folder else self.common
        return adapt_settings(self.overrides.get(video.path, inherited), video)

    def output_for(self, video):
        if self.preserve_tree and video.root:
            relative = os.path.relpath(os.path.dirname(video.path), os.path.dirname(video.root))
            return os.path.join(self.output, relative)
        return self.output

    def commands(self):
        outputs = {}
        result = []
        for video in self.selected:
            settings = self.settings_for(video)
            if not settings.values.get('voice'):
                raise ValueError(f'Choisissez une voix pour {Path(video.path).name}.')
            output = self.output_for(video)
            collision_key = os.path.normcase(os.path.abspath(os.path.join(output, Path(video.path).stem)))
            if collision_key in outputs:
                raise ValueError('Deux vidéos portent le même nom dans la même sortie. Activez la conservation de l’arborescence ou créez des lots séparés.')
            outputs[collision_key] = video.path
            flags = dict.fromkeys(BOOLS, False)
            flags.update(translate=settings.translate, skip_existing=self.resume,
                         overwrite=not self.resume, dry_run=self.dry_run)
            result.append((video, batch_command(settings.values, flags, [video.path], output)))
        if not result:
            raise ValueError('Sélectionnez au moins une vidéo avec des sous-titres et une piste audio.')
        return result


def discover(sources, recursive):
    """Ordre stable : fichiers du dossier puis ses sous-dossiers, sans suivre les liens."""
    result, seen = [], set()
    for source in sources:
        source = os.path.abspath(source)
        if os.path.isfile(source):
            candidates = [(source, '')] if Path(source).suffix.lower() in VIDEO_EXTENSIONS else []
        elif os.path.isdir(source):
            candidates = []
            def report(error):
                raise error
            for folder, dirs, files in os.walk(source, onerror=report, followlinks=False):
                dirs[:] = sorted([d for d in dirs if not os.path.islink(os.path.join(folder, d))], key=str.casefold) if recursive else []
                for name in sorted(files, key=str.casefold):
                    if Path(name).suffix.lower() in VIDEO_EXTENSIONS:
                        candidates.append((os.path.join(folder, name), source))
        else:
            raise ValueError(f'Chemin introuvable : {source}')
        for path, root in candidates:
            key = os.path.normcase(path)
            if key not in seen:
                result.append(Video(path, root))
                seen.add(key)
    return result


def inspect_video(video):
    """Détection bornée par fichier ; aucune écriture dans les médias."""
    from add_dub.core.subtitles import find_sidecar_srt, _srt_in_srt_dir_for_video
    result = deepcopy(video)
    result.audio, result.subtitles, result.error = [], [], ''
    try:
        process = subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', video.path],
                                 capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30,
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if process.returncode:
            raise ValueError(process.stderr.strip() or 'Vidéo illisible')
        streams = json.loads(process.stdout).get('streams', [])
        sidecar = _srt_in_srt_dir_for_video(video.path) or find_sidecar_srt(video.path)
        if sidecar:
            result.subtitles.append(Track('srt', f'SRT externe - {Path(sidecar).name}', kind='srt'))
        sub_index = 0
        for stream in streams:
            kind = stream.get('codec_type')
            if kind not in ('audio', 'subtitle'):
                continue
            tags = stream.get('tags') or {}
            language, title = tags.get('language', ''), tags.get('title', '')
            codec = stream.get('codec_name', '?')
            description = ' · '.join(x for x in (language or 'Langue inconnue', title, codec) if x)
            if kind == 'audio':
                result.audio.append(Track(str(stream['index']), f'Piste {len(result.audio) + 1} - {description}', language, title, 'audio', len(result.audio)))
            else:
                # MKV conserve l'extraction et l'OCR existants ; les autres conteneurs passent par FFmpeg.
                mode = 'mkv' if Path(video.path).suffix.lower() == '.mkv' else 'stream'
                value = f'{mode}:{sub_index if mode == "mkv" else stream["index"]}'
                result.subtitles.append(Track(value, f'Piste {sub_index + 1} - {description}', language, title, mode, sub_index))
                sub_index += 1
    except Exception as exc:
        result.error = f'Détection impossible : {exc}'
    result.selected = video.selected and result.eligible
    return result
