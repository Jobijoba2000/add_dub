# add_dub/adapters/subtitle_edit.py
import os
import re
import subprocess
import shutil
import threading
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
    with _SETTINGS_LOCK:
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
    if not os.path.exists(target_file):
        from add_dub.logger import logger as log
        log.info(f"Téléchargement du modèle OCR Tesseract pour la langue '{tess_code}' ({tess_code}.traineddata)...")
        url = f"https://github.com/tesseract-ocr/tessdata/raw/main/{tess_code}.traineddata"
        try:
            import urllib.request
            urllib.request.urlretrieve(url, target_file)
            log.info(f"Modèle OCR Tesseract '{tess_code}.traineddata' téléchargé avec succès.")
        except Exception as e:
            log.warning(f"Échec du téléchargement du modèle OCR {tess_code} : {e}")

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
    if not os.path.exists(target_file):
        from add_dub.logger import logger as log
        log.info(f"Téléchargement du dictionnaire de correction OCR ({tess_code}_OCRFixReplaceList.xml)...")
        url = f"https://raw.githubusercontent.com/SubtitleEdit/subtitleedit/main/Dictionaries/{tess_code}_OCRFixReplaceList.xml"
        try:
            import urllib.request
            urllib.request.urlretrieve(url, target_file)
            log.info(f"Dictionnaire OCR '{tess_code}_OCRFixReplaceList.xml' téléchargé avec succès.")
        except Exception as e:
            log.warning(f"Échec du téléchargement du dictionnaire OCR {tess_code} : {e}")

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
    return_code = process.wait()
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
