# add_dub/adapters/subtitle_edit.py
import os
import re
import subprocess
import shutil
import threading
from filelock import FileLock
from contextlib import contextmanager
from add_dub.io.fs import ROOT

def _find_exe(candidates):
    for c in candidates:
        if os.path.exists(c):
            return c
        p = shutil.which(c)
        if p:
            return p
    return None

LANG_TO_TESS = {
    "fr": "fra", "fre": "fra", "fra": "fra",
    "es": "spa", "spa": "spa",
    "en": "eng", "eng": "eng",
    "pl": "pol", "pol": "pol",
    "de": "deu", "ger": "deu", "deu": "deu",
    "it": "ita", "ita": "ita",
    "ja": "jpn", "jpn": "jpn",
    "ru": "rus", "rus": "rus",
    "pt": "por", "por": "por",
    "nl": "nld", "dut": "nld", "nld": "nld",
    "tr": "tur", "tur": "tur",
    "uk": "ukr", "ukr": "ukr",
    "zh": "chi_sim", "zho": "chi_sim", "chi": "chi_sim",
    "ko": "kor", "kor": "kor",
    "ar": "ara", "ara": "ara",
}

_SETTINGS_LOCK = threading.Lock()


@contextmanager
def _subtitle_edit_language(settings_file: str, language: str):
    """Force la langue avant le lancement, puis libère immédiatement le verrou."""
    if not settings_file or not os.path.isfile(settings_file) or not language:
        yield
        return
    with _SETTINGS_LOCK, FileLock(settings_file + ".lock", timeout=120):
        with open(settings_file, "r", encoding="utf-8") as stream:
            text = stream.read()
        updated, count = re.subn(
            r"(<TesseractLastLanguage>)(.*?)(</TesseractLastLanguage>)",
            lambda match: f"{match.group(1)}{language}{match.group(3)}",
            text,
            count=1,
        )
        if count:
            with open(settings_file, "w", encoding="utf-8", newline="") as stream:
                stream.write(updated)
        yield

def ensure_tesseract_lang(lang_code: str) -> str:
    """
    Vérifie si le fichier .traineddata pour la langue donnée est présent dans Tesseract.
    Si absent, le télécharge automatiquement depuis le dépôt officiel Tesseract.
    """
    if not lang_code:
        return "fra"
    tess_code = LANG_TO_TESS.get(lang_code.lower(), lang_code.lower())
    tessdata_dir = os.path.join(ROOT, "tools", "subtitle_edit", "Tesseract550", "tessdata")
    if not os.path.exists(tessdata_dir):
        return tess_code

    target_file = os.path.join(tessdata_dir, f"{tess_code}.traineddata")
    from add_dub.adapters.downloads import resource
    from add_dub.adapters.models import revisions
    from add_dub.io.work import is_offline
    if not re.fullmatch(r'[a-z_]+', tess_code):
        raise ValueError('Code de langue OCR invalide.')
    resource(f"https://github.com/tesseract-ocr/tessdata/raw/{revisions()['ocr_tessdata']}/{tess_code}.traineddata",
             target_file, offline=is_offline())

    return tess_code

def ensure_ocr_fix_list(lang_code: str) -> None:
    """
    Vérifie si le dictionnaire de correction d'erreurs OCR (<lang>_OCRFixReplaceList.xml) est présent.
    Si absent, le télécharge automatiquement depuis le dépôt SubtitleEdit GitHub.
    """
    if not lang_code:
        return
    tess_code = LANG_TO_TESS.get(lang_code.lower(), lang_code.lower())
    dict_dir = os.path.join(ROOT, "tools", "subtitle_edit", "Dictionaries")
    if not os.path.exists(dict_dir):
        return

    target_file = os.path.join(dict_dir, f"{tess_code}_OCRFixReplaceList.xml")
    from add_dub.adapters.downloads import resource
    from add_dub.adapters.models import revisions
    from add_dub.io.work import is_offline
    if not re.fullmatch(r'[a-z_]+', tess_code):
        raise ValueError('Code de langue OCR invalide.')
    # Dictionnaire facultatif ; l'absence n'empêche pas la reconnaissance.
    try:
        resource(f"https://raw.githubusercontent.com/SubtitleEdit/subtitleedit/{revisions()['ocr_dictionary']}/Dictionaries/{tess_code}_OCRFixReplaceList.xml",
                 target_file, offline=is_offline())
    except Exception as exc:
        from add_dub.logger import logger
        logger.warning('Dictionnaire OCR indisponible : %s', exc)


def subtitle_edit_ocr(ocr_input, output_path, lang="fr", cwd=None):
    """
    Utilise Subtitle Edit pour OCR -> SRT.
    Retourne True si output_path est créé et non vide, sinon False.
    """
    se = _find_exe([
        os.path.join(ROOT, "tools", "subtitle_edit", "SubtitleEdit.exe"),
        "SubtitleEdit", 
        "SubtitleEdit.exe",
    ])
    if not se:
        return False

    tess_lang = ensure_tesseract_lang(lang)
    ensure_ocr_fix_list(lang)

    cmd = [
        se, "/convert", ocr_input, "subrip",
        f"/outputfilename:{output_path}",
        "/encoding:utf-8",
        "/ocrengine:tesseract",
        "/FixCommonErrors",
        "/overwrite",
    ]
    settings_file = os.path.join(os.path.dirname(se), "Settings.xml")
    # Subtitle Edit 4.0.13 ne propose pas la langue Tesseract en argument CLI.
    # Son Settings.xml est ajusté avant son lancement et lu à son démarrage.
    with _subtitle_edit_language(settings_file, tess_lang):
        process = subprocess.Popen(cmd, cwd=cwd)
        try:
            return_code = process.wait(timeout=600)
        except BaseException:
            process.kill()
            process.wait()
            raise
    if return_code:
        raise subprocess.CalledProcessError(return_code, cmd)
    return os.path.exists(output_path) and os.path.getsize(output_path) > 0

def vobsub2srt_ocr(base_noext, lang="fr", cwd=None):
    """
    Utilise vobsub2srt si dispo. Retourne chemin .srt produit ou None.
    base_noext = chemin sans extension (ex: C:\\...\\video)
    """
    exe = _find_exe(["vobsub2srt", "vobsub2srt.exe"])
    if not exe:
        return None
    cmd = [exe, "--lang", lang, base_noext]
    subprocess.run(cmd, check=True, cwd=cwd)
    produced = base_noext + ".srt"
    if os.path.exists(produced) and os.path.getsize(produced) > 0:
        return produced
    return None
