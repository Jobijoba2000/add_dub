# add_dub/adapters/subtitle_edit.py
import os
import subprocess
import shutil

def _find_exe(candidates):
    for c in candidates:
        p = shutil.which(c)
        if p:
            return p
        if os.path.exists(c):
            return c
    return None

def subtitle_edit_ocr(ocr_input, output_path, cwd=None):
    """
    Utilise Subtitle Edit pour OCR -> SRT.
    Retourne True si output_path est créé et non vide, sinon False.
    """
    se = _find_exe([
        "SubtitleEdit", "SubtitleEdit.exe",
        r"C:\Program Files\Subtitle Edit\SubtitleEdit.exe",
        r"C:\Program Files (x86)\Subtitle Edit\SubtitleEdit.exe",
    ])
    if not se:
        return False

    cmd = [
        se, "/convert", ocr_input, "subrip",
        f"/outputfilename:{output_path}",
        "/encoding:utf-8",
        "/ocrengine:tesseract",
        "/overwrite",
    ]
    subprocess.run(cmd, check=True, cwd=cwd)
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
