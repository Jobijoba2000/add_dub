"""Mise à jour explicite des révisions des ressources distantes."""
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
URLS = {
    'ocr_tessdata': 'https://api.github.com/repos/tesseract-ocr/tessdata/commits/main',
    'ocr_dictionary': 'https://api.github.com/repos/SubtitleEdit/subtitleedit/commits/main',
    'michaelfeil/ct2fast-opus-mt-en-fr': 'https://huggingface.co/api/models/michaelfeil/ct2fast-opus-mt-en-fr',
    'michaelfeil/ct2fast-opus-mt-fr-en': 'https://huggingface.co/api/models/michaelfeil/ct2fast-opus-mt-fr-en',
    'osa911/nllb-200-distilled-600M-ct2-int8': 'https://huggingface.co/api/models/osa911/nllb-200-distilled-600M-ct2-int8',
}


def main():
    revisions = {}
    for name, url in URLS.items():
        with urllib.request.urlopen(url, timeout=30) as response:
            revisions[name] = json.load(response)['sha']
    target = ROOT / 'models.lock.json'
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(revisions, indent=2) + '\n', encoding='utf-8')
    temporary.replace(target)
    print(f'{len(revisions)} révisions enregistrées dans {target.name}.')


if __name__ == '__main__':
    main()
