"""Lecture sans effets de bord et écriture atomique des paramètres généraux."""
import math
import os
import re
import tempfile
from pathlib import Path

DEFAULTS = dict(input_dir='input', output_dir='output', tmp_dir='tmp', language='auto',
                tts_engine='onecore', voice_id='', min_rate_tts=1.0, max_rate_tts=1.8,
                db=-5.0, offset=0, offset_video=0, bg=1.0, tts=1.0,
                audio_codec='ac3', audio_bitrate=320, orig_audio_lang='Original',
                ask_test_before_cleanup=False, translate=False, translate_to='fr',
                translate_from='auto', translation_engine='ctranslate2', reuse_translated_subs=True)
DEFAULTS.update({'logging.console_enable': True, 'logging.console_level': 'INFO',
                 'logging.file_enable': True, 'logging.file_level': 'DEBUG',
                 'logging.file_name': 'add_dub.log', 'logging.dir': 'logs'})
FLOATS = {'db', 'bg', 'tts', 'min_rate_tts', 'max_rate_tts'}
INTS = {'offset', 'offset_video', 'audio_bitrate'}
BOOLS = {key for key, value in DEFAULTS.items() if isinstance(value, bool)}
ASSIGNMENT = re.compile(r'^(\s*)([\w.]+)(\s*=\s*)(.*)$')


def settings_path():
    return Path(os.environ.get('ADD_DUB_OPTIONS', 'options.conf')).resolve()


def split_comment(value):
    quote = None
    for i, char in enumerate(value):
        if char in '\"\'':
            if quote == char:
                quote = None
            elif quote is None:
                quote = char
        elif char in '#;' and quote is None:
            return value[:i], value[i:]
    return value, ''


def read_settings(path=None):
    values = dict(DEFAULTS)
    path = Path(path) if path else settings_path()
    if not path.exists():
        return values
    section = ''
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        stripped = line.strip()
        if stripped.startswith('[') and stripped.endswith(']'):
            section = stripped[1:-1].lower()
            continue
        match = ASSIGNMENT.match(line)
        if not match:
            continue
        key = (section + '.' if section else '') + match[2].lower()
        if key not in DEFAULTS:
            continue
        value = re.sub(r'\s+d\s*$', '', split_comment(match[4])[0]).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in '\"\'':
            value = value[1:-1]
        if key in BOOLS:
            value = value.lower() in ('true', 'yes', 'on', '1')
        elif key in FLOATS | INTS:
            try:
                value = int(value) if key in INTS else float(value)
            except ValueError:
                pass  # Show invalid existing input rather than replacing it silently.
        values[key] = value
    return values


def number_limits(key, values):
    if key in ('min_rate_tts', 'max_rate_tts'):
        return (.5, 6.0) if values.get('tts_engine') == 'onecore' else (.1, 10.0)
    if key == 'audio_bitrate':
        codec = values.get('audio_codec')
        return (32, 640) if codec == 'ac3' else (8, 320) if codec == 'mp3' else (6, 510) if codec in ('opus', 'libopus') else (8, 1536)
    return {'db': (-100.0, 0.0), 'bg': (0.0, 10.0), 'tts': (0.0, 10.0),
            'offset': (-3600000, 3600000), 'offset_video': (-3600000, 3600000),
            'audio_bitrate': (8, 1536)}[key]


def validate_settings(values):
    errors = {}
    numbers = {}
    for key in FLOATS | INTS:
        raw = str(values.get(key, ''))
        try:
            if ',' in raw or (key in INTS and not re.fullmatch(r'[+-]?\d+', raw)):
                raise ValueError()
            number = float(raw)
            low, high = number_limits(key, values)
            if not math.isfinite(number) or not low <= number <= high:
                raise ValueError()
            numbers[key] = number
        except (ValueError, TypeError):
            low, high = number_limits(key, values)
            errors[key] = f'Valeur attendue : {low:g} à {high:g}' + (' (entier).' if key in INTS else ' (point décimal).')
    if values.get('audio_codec') == 'ac3' and 'audio_bitrate' in numbers:
        if numbers['audio_bitrate'] not in (32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 384, 448, 512, 576, 640):
            errors['audio_bitrate'] = 'Débit AC3 standard requis : 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 384, 448, 512, 576 ou 640.'
    if numbers.get('min_rate_tts', 0) > numbers.get('max_rate_tts', 10):
        errors['min_rate_tts'] = errors['max_rate_tts'] = 'La vitesse minimale doit être inférieure ou égale à la maximale.'
    choices = {'tts_engine': ('onecore', 'edge', 'gtts'), 'language': ('auto', 'fr', 'en', 'es', 'de', 'it'),
               'audio_codec': ('ac3', 'aac', 'mp3', 'opus', 'libopus', 'vorbis', 'libvorbis', 'flac', 'pcm_s16le'),
               'translation_engine': ('ctranslate2', 'google')}
    for key in ('logging.console_level', 'logging.file_level'):
        choices[key] = ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')
    for key, allowed in choices.items():
        if values.get(key) not in allowed:
            errors[key] = 'Choisissez une valeur dans la liste.'
    if values.get('translate'):
        for key in ('translate_from', 'translate_to'):
            text = str(values.get(key, ''))
            if not re.fullmatch(r'[a-z]{2}', text) and not (key == 'translate_from' and text in ('auto', '')):
                errors[key] = 'Code de langue à deux lettres : fr, en, es… (auto pour la source).'
    for key in ('input_dir', 'output_dir', 'tmp_dir', 'logging.dir', 'logging.file_name'):
        if not str(values.get(key, '')).strip():
            errors[key] = 'Ce champ ne peut pas être vide.'
    name = str(values.get('logging.file_name', ''))
    if any(c in name for c in '<>:"/\\|?*') or name in ('.', '..'):
        errors['logging.file_name'] = 'Indiquez un nom de fichier sans dossier ni caractère interdit.'
    for key, value in values.items():
        if isinstance(value, str) and any(c in value for c in '\r\n\0'):
            errors[key] = 'Les sauts de ligne ne sont pas autorisés.'
    # These fields retain their values while their feature is disabled.
    disabled = []
    if not values.get('translate'):
        disabled += ['translation_engine', 'translate_from', 'translate_to']
    if not values.get('logging.console_enable'):
        disabled += ['logging.console_level']
    if not values.get('logging.file_enable'):
        disabled += ['logging.file_level', 'logging.file_name', 'logging.dir']
    # Bitrate must remain a parseable integer even when ignored by lossless codecs.
    for key in disabled:
        errors.pop(key, None)
    return errors


def save_settings(values, path=None):
    errors = validate_settings(values)
    if errors:
        raise ValueError('\n'.join(f'{key} : {message}' for key, message in errors.items()))
    path = Path(path) if path else settings_path()
    raw = path.read_bytes() if path.exists() else b''
    encoding = 'utf-8-sig' if raw.startswith(b'\xef\xbb\xbf') else 'utf-8'
    newline = '\r\n' if b'\r\n' in raw else '\n'
    lines = raw.decode(encoding).splitlines()
    def serialize(key):
        value = values[key]
        if key in BOOLS:
            return 'true' if value else 'false'
        if key in FLOATS:
            return f'{float(value):.1f}'
        if key in INTS:
            return str(int(value))
        text = str(value)
        quote = '"' if '"' not in text else "'"
        if quote in text:
            raise ValueError(f'{key} : les deux types de guillemets ne peuvent pas être combinés.')
        return quote + text + quote
    written, section, output = set(), '', []
    # Add missing root keys before the first section, never inside [logging].
    def missing_root():
        for key in values:
            if key in DEFAULTS and '.' not in key and key not in written:
                output.append(f'{key} = {serialize(key)}')
                written.add(key)
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('[') and stripped.endswith(']'):
            if not section:
                missing_root()
            section = stripped[1:-1].lower()
        match = ASSIGNMENT.match(line)
        key = ((section + '.') if section else '') + match[2].lower() if match else None
        if key in DEFAULTS and key in values:
            value, comment = split_comment(match[4])
            flag = ' d' if re.search(r'\s+d\s*$', value) else ''
            line = f'{match[1]}{match[2]}{match[3]}{serialize(key)}{flag}' + ('  ' + comment if comment else '')
            written.add(key)
        output.append(line)
    if not section:
        missing_root()
    remaining = [key for key in values if key in DEFAULTS and key not in written]
    if remaining:
        # A repeated section is accepted by the loader; keeps all original sections intact.
        output += ['', '[logging]']
        output += [f'{key.split(".", 1)[1]} = {serialize(key)}' for key in remaining]
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write((newline.join(output) + newline).encode(encoding))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
