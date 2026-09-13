"""Langues des pistes de sortie, indépendantes de leurs titres affichés."""
import json
import re
import subprocess

CODES = dict(pair.split(':') for pair in (
    'fr:fra en:eng ja:jpn de:deu es:spa it:ita pt:por ru:rus zh:zho ko:kor '
    'ar:ara el:ell cs:ces ro:ron nl:nld sv:swe vi:vie tr:tur pl:pol da:dan '
    'fi:fin no:nor nb:nob nn:nno hi:hin id:ind th:tha he:heb uk:ukr bg:bul '
    'hr:hrv sk:slk sl:slv hu:hun ca:cat fa:fas ta:tam te:tel bn:ben '
    'ur:urd ms:msa fil:fil tl:tgl af:afr sw:swa et:est lv:lav lt:lit '
    'is:isl ga:gle cy:cym eu:eus gl:glg mk:mkd sq:sqi sr:srp bs:bos '
    'az:aze hy:hye ka:kat kk:kaz uz:uzb mn:mon ne:nep si:sin km:khm '
    'lo:lao my:mya ml:mal mr:mar gu:guj kn:kan pa:pan'
).split())

# English display names, kept local so metadata handling needs no network/service.
NAMES = dict(zip(CODES.values(), (
    'French|English|Japanese|German|Spanish|Italian|Portuguese|Russian|Chinese|Korean|'
    'Arabic|Greek|Czech|Romanian|Dutch|Swedish|Vietnamese|Turkish|Polish|Danish|'
    'Finnish|Norwegian|Norwegian Bokmål|Norwegian Nynorsk|Hindi|Indonesian|Thai|Hebrew|Ukrainian|Bulgarian|'
    'Croatian|Slovak|Slovenian|Hungarian|Catalan|Persian|Tamil|Telugu|Bengali|'
    'Urdu|Malay|Filipino|Tagalog|Afrikaans|Swahili|Estonian|Latvian|Lithuanian|'
    'Icelandic|Irish|Welsh|Basque|Galician|Macedonian|Albanian|Serbian|Bosnian|'
    'Azerbaijani|Armenian|Georgian|Kazakh|Uzbek|Mongolian|Nepali|Sinhala|Khmer|'
    'Lao|Burmese|Malayalam|Marathi|Gujarati|Kannada|Punjabi'
).split('|')))
BIBLIOGRAPHIC = dict(pair.split(':') for pair in (
    'fre:fra ger:deu chi:zho gre:ell cze:ces rum:ron dut:nld slo:slk '
    'per:fas may:msa ice:isl wel:cym baq:eus mac:mkd alb:sqi arm:hye geo:kat bur:mya'
).split())
NAME_CODES = {name.casefold(): code for code, name in NAMES.items()}
NAME_CODES.update({'日本語': 'jpn', 'français': 'fra', 'deutsch': 'deu',
                   'español': 'spa', 'português': 'por', 'italiano': 'ita',
                   'русский': 'rus', '中文': 'zho', '한국어': 'kor'})


def language_code(value):
    value = str(value or '').strip().casefold()
    if value in NAME_CODES:
        return NAME_CODES[value]
    # Accept locale subtags, but do not turn arbitrary malformed strings into codes.
    if not re.fullmatch(r'[a-z]{2,3}(?:[-_][a-z0-9]{2,8})*', value):
        return 'und'
    code = value.replace('_', '-').split('-')[0]
    if code in CODES:
        return CODES[code]
    return code if code in NAMES or code in BIBLIOGRAPHIC else 'und'


def language_name(value):
    code = language_code(value)
    return NAMES.get(BIBLIOGRAPHIC.get(code, code), 'Unknown language')


def track_language(stream):
    tags = {str(k).casefold().replace('_', '').replace('-', ''): v
            for k, v in (stream.get('tags') or {}).items()}
    # Prefer modern locale metadata when it is exposed by the demuxer.
    for key in ('languagebcp47', 'languageietf', 'language'):
        code = language_code(tags.get(key))
        if code != 'und':
            return code
    # Only standalone language labels, optionally separated from annotations.
    # Never infer from filenames, other tracks or free-form prose.
    parts = re.split(r'[\[\](){}|/·,:]|\s+-\s+|\s+->\s+', str(tags.get('title', '')))
    codes = {BIBLIOGRAPHIC.get(code, code) for part in parts
             if (code := language_code(part)) != 'und'}
    return codes.pop() if len(codes) == 1 else 'und'


def source_languages(path, audio_index, sub_choice):
    result = subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', path],
                            capture_output=True, text=True, encoding='utf-8', errors='replace',
                            timeout=30, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    result.check_returncode()
    streams = json.loads(result.stdout).get('streams', [])
    audio = next((s for s in streams if s.get('codec_type') == 'audio'
                  and (audio_index is None or s['index'] == int(audio_index))), {})
    subtitle = {}
    if sub_choice and sub_choice[0] in ('mkv', 'stream'):
        candidates = [s for s in streams if s.get('codec_type') == 'subtitle']
        index = int(sub_choice[1])
        if sub_choice[0] == 'mkv':
            subtitle = candidates[index] if 0 <= index < len(candidates) else {}
        else:
            subtitle = next((s for s in candidates if s['index'] == index), {})
    return track_language(audio), track_language(subtitle)


def voice_locale(voice_id, voices):
    """Return the voice's locale without inventing a region for language-only IDs."""
    for voice in voices:
        if voice.get('id') == voice_id:
            locale = str(voice.get('lang') or '').strip().replace('_', '-')
            if re.fullmatch(r'[a-zA-Z]{2,3}(?:-[a-zA-Z]{4})?-(?:[a-zA-Z]{2}|[0-9]{3})', locale):
                parts = locale.split('-')
                return '-'.join([parts[0].lower()] +
                                [p.title() if len(p) == 4 else p.upper() for p in parts[1:]])
    match = re.search(r'(?:^|[_\\])([a-z]{2})-?([A-Z]{2})(?:[-_]|$)', str(voice_id or ''))
    return f'{match[1]}-{match[2]}' if match else ''


def dubbed_track_title(language, locale):
    name = language_name(language)
    return f'{name} [{locale}]' if locale and language_code(locale) == language_code(language) else name


def voice_language(voice_id, voices):
    for voice in voices:
        if voice.get('id') == voice_id:
            code = language_code(voice.get('lang'))
            if code != 'und':
                return code
    if str(voice_id or '') in CODES:
        return language_code(voice_id)
    # Edge locale or Windows token locale, never arbitrary letters in an ID.
    match = re.search(r'(?:^|[_\\])([a-z]{2})-?[A-Z]{2}(?:[-_]|$)', str(voice_id or ''))
    return language_code(match[1]) if match else 'und'


def external_subtitle_language(path, explicit=None):
    code = language_code(explicit)
    if code != 'und':
        return code
    from pathlib import Path
    suffix = Path(path).stem.rsplit('.', 1)[-1]
    if suffix in CODES or suffix in CODES.values():
        return language_code(suffix)
    try:
        from langdetect import DetectorFactory
        from add_dub.core.subtitles import parse_srt_file
        text = ' '.join(t for _, _, t in parse_srt_file(path))[:20000]
        if len(text.strip()) < 80:
            return 'und'
        factory = DetectorFactory()
        from langdetect.detector_factory import PROFILES_DIRECTORY
        factory.load_profile(PROFILES_DIRECTORY)
        factory.seed = 0
        detector = factory.create()
        detector.append(text)
        results = detector.get_probabilities()
        if results and results[0].prob >= 0.95:
            return language_code(results[0].lang)
    except Exception:
        pass
    return 'und'
