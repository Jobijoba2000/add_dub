# add_dub/core/subtitles.py

import os
import re
import html
import time
import shutil
import subprocess
import tempfile

import add_dub.io.fs as io_fs  # ← module, pas des valeurs copiées
from add_dub.adapters.mkvtoolnix import mkv_has_subtitle_track, mkvmerge_identify_json
from add_dub.adapters.subtitle_edit import subtitle_edit_ocr, vobsub2srt_ocr


def _find_exe(candidates):
    for c in candidates:
        p = shutil.which(c)
        if p:
            return p
        if os.path.exists(c):
            return c
    return None


def find_sidecar_srt(video_path: str) -> str | None:
    base, _ = os.path.splitext(video_path)
    candidates = [base + ".srt", base + ".SRT"]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def _srt_in_srt_dir_for_video(video_path: str) -> str | None:
    """
    Retourne le chemin srt/<video_base>.srt s'il existe, sinon None.
    """
    base = os.path.splitext(os.path.basename(video_path))[0] + ".srt"
    dst = io_fs.join_srt(base)
    return dst if os.path.exists(dst) else None


def _copy_into_srt_dir(src_srt_path: str, video_fullpath: str) -> str:
    """
    Copie un SRT (sidecar) vers srt/<video_base>.srt et retourne le chemin de destination.
    Ne crée jamais rien dans le répertoire source.
    """
    base = os.path.splitext(os.path.basename(video_fullpath))[0] + ".srt"
    dst = io_fs.join_srt(base)
    os.makedirs(os.path.dirname(dst), exist_ok=True)

    # Si la source est déjà dans srt/ avec le bon nom, on garde tel quel.
    if os.path.abspath(src_srt_path) != os.path.abspath(dst):
        shutil.copy2(src_srt_path, dst)
    return dst


def strip_subtitle_tags_inplace(path: str) -> None:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    blocks = re.split(r"\n\s*\n", content.strip())
    cleaned_blocks = []
    for b in blocks:
        lines = b.splitlines()
        if len(lines) >= 3 and re.match(
            r"\d{2}:\d{2}:\d{2},\d{3}\s*-->\s*\d{2}:\d{2}:\d{2},\d{3}", lines[1]
        ):
            header = lines[:2]
            text_lines = lines[2:]
            new_text = []
            for t in text_lines:
                t = html.unescape(t)
                t = re.sub(r"<[^>]+>", "", t)
                t = re.sub(r"\{\\[^}]*\}", "", t)
                t = re.sub(r"\s{2,}", " ", t).strip()
                new_text.append(t)
            new_text = [x for x in new_text if x]
            cleaned_blocks.append("\n".join(header + (new_text or [""])))
        else:
            cleaned_blocks.append(b)
    cleaned = "\n\n".join(cleaned_blocks) + "\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(cleaned)


def time_to_seconds(t_str: str) -> float:
    h, m, s_ms = t_str.split(":")
    s, ms = s_ms.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def parse_srt_file(srt_file: str, duration_limit_sec: int | None = None):
    with open(srt_file, encoding="utf-8") as f:
        content = f.read()
    blocks = re.split(r"\n\s*\n", content.strip())
    subtitles = []
    for block in blocks:
        lines = block.splitlines()
        if len(lines) >= 3:
            m = re.match(
                r"(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d{3})",
                lines[1],
            )
            if not m:
                continue
            start = time_to_seconds(m.group(1).replace(".", ","))
            end = time_to_seconds(m.group(2).replace(".", ","))
            if duration_limit_sec is not None and start >= duration_limit_sec:
                continue
            if duration_limit_sec is not None and end > duration_limit_sec:
                end = float(duration_limit_sec)
            text = " ".join(lines[2:]).strip()
            subtitles.append((start, end, text))
    return subtitles


def list_input_videos():
    """
    Retourne les fichiers éligibles situés dans le dossier d’entrée **actuel** :
    - MKV : affiché si au moins une piste ST intégrée OU SRT sidecar présent OU SRT homonyme dans srt/.
    - MP4/AVI : affiché si SRT sidecar présent OU SRT homonyme dans srt/.
    """
    input_dir = io_fs.INPUT_DIR
    try:
        files = os.listdir(input_dir)
    except FileNotFoundError:
        files = []

    candidates = []
    for f in files:
        full = io_fs.join_input(f)
        if not os.path.isfile(full):
            continue
        fl = f.lower()
        srt_in_srt = _srt_in_srt_dir_for_video(full) is not None

        if fl.endswith(".mkv"):
            sidecar = find_sidecar_srt(full)
            if srt_in_srt or sidecar or mkv_has_subtitle_track(full):
                candidates.append(f)
        elif fl.endswith(".mp4") or fl.endswith(".avi"):
            sidecar = find_sidecar_srt(full)
            if srt_in_srt or sidecar:
                candidates.append(f)
    return sorted(candidates, key=lambda x: x.lower())


def extract_first_subtitle_to_srt_into_input(
    video_fullpath: str, local_sub_index: int = 0, ocr_lang: str = "fr"
) -> str | None:
    """
    ⚠️ Comportement modifié :
    - Extraction/convert texte/ocr → **toujours** dans srt/<video_base>.srt
    - Jamais d'écriture dans le dossier source (input).
    """
    info = mkvmerge_identify_json(video_fullpath)
    if not info:
        print("MKVToolNix requis pour identifier les pistes (mkvmerge).")
        return None

    sub_tracks = [t for t in info.get("tracks", []) if t.get("type") == "subtitles"]
    if not sub_tracks:
        print("Aucune piste de sous-titres intégrée.")
        return None

    if local_sub_index < 0 or local_sub_index >= len(sub_tracks):
        local_sub_index = 0
    t_sel = sub_tracks[local_sub_index]
    track_id = t_sel.get("id")
    codec_id = (t_sel.get("properties", {}).get("codec_id") or "").lower()

    base = os.path.splitext(os.path.basename(video_fullpath))[0]
    target_srt = io_fs.join_srt(base + ".srt")
    os.makedirs(os.path.dirname(target_srt), exist_ok=True)

    # Pistes texte -> conversion directe en SRT via ffmpeg
    is_text = codec_id.startswith("s_text/")
    if is_text:
        try:
            cmd = [
                "ffmpeg",
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-stats",
                "-i",
                video_fullpath,
                "-map",
                f"0:s:{local_sub_index}",
                "-c:s",
                "subrip",
                target_srt,
            ]
            start = time.perf_counter()
            subprocess.run(
                cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            end = time.perf_counter()
            print(end - start)
            if os.path.exists(target_srt) and os.path.getsize(target_srt) > 0:
                strip_subtitle_tags_inplace(target_srt)
                print(f"SRT extrait (texte) -> {target_srt}")
                return target_srt
            print("Échec extraction SRT (texte).")
        except subprocess.CalledProcessError as e:
            print("Erreur ffmpeg extraction ST texte:", (e.stderr or "")[-400:])
        return None

    # Bitmap (PGS/VobSub) -> mkvextract + OCR
    mkvextract = _find_exe(
        [
            "mkvextract",
            r"C:\Program Files\MKVToolNix\mkvextract.exe",
            r"C:\Program Files (x86)\MKVToolNix\mkvextract.exe",
        ]
    )
    if not mkvextract:
        print("mkvextract introuvable.")
        return None

    tmp_dir = tempfile.mkdtemp(prefix="subs_")
    try:
        ext = ".sup" if "pgs" in codec_id or "hdmv/pgs" in codec_id else ".sub"
        base_noext = os.path.join(tmp_dir, base)
        ocr_input = base_noext + ext

        cmd = ["mkvextract", "tracks", video_fullpath, f"{track_id}:{ocr_input}"]
        if os.path.basename(mkvextract).lower() != "mkvextract":
            cmd[0] = mkvextract
        subprocess.run(
            cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )

        tmp_out = os.path.join(tmp_dir, base + ".srt")

        ok = subtitle_edit_ocr(ocr_input, tmp_out, cwd=tmp_dir)
        if ok:
            os.makedirs(os.path.dirname(target_srt), exist_ok=True)
            os.replace(tmp_out, target_srt)
            strip_subtitle_tags_inplace(target_srt)
            print(f"SRT OCR (Subtitle Edit) -> {target_srt}")
            return target_srt

        if ext == ".sub":
            produced = vobsub2srt_ocr(base_noext, lang=ocr_lang, cwd=tmp_dir)
            if produced:
                os.makedirs(os.path.dirname(target_srt), exist_ok=True)
                os.replace(produced, target_srt)
                strip_subtitle_tags_inplace(target_srt)
                print(f"SRT OCR (vobsub2srt) -> {target_srt}")
                return target_srt

        print("Aucun OCR disponible.")
        return None
    finally:
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass


def resolve_srt_for_video(video_fullpath: str, sub_choice_global: tuple) -> str | None:
    """
    Politique unifiée (jamais d'écriture dans le dossier source) :
      1) Si srt/<base>.srt existe déjà → on l'utilise.
      2) Sinon, si un sidecar .srt est à côté de la vidéo → on le COPIE dans srt/ et on utilise la copie.
      3) Sinon, si on a une piste intégrée (cas MKV) → extraction vers srt/ et on l'utilise.
    """
    # 1) Priorité au SRT déjà présent dans srt/
    srt_in_srt = _srt_in_srt_dir_for_video(video_fullpath)
    if srt_in_srt:
        strip_subtitle_tags_inplace(srt_in_srt)
        return srt_in_srt

    kind, value = sub_choice_global

    # 2) Sidecar à côté de la vidéo → copie dans srt/
    sidecar = find_sidecar_srt(video_fullpath)
    if sidecar:
        dst = _copy_into_srt_dir(sidecar, video_fullpath)
        strip_subtitle_tags_inplace(dst)
        return dst

    # 3) Extraction depuis piste intégrée (typiquement MKV)
    #    (Que l'utilisateur ait choisi "mkv" ou que 'kind' soit autre, on tente l'extraction.)
    srt_path = extract_first_subtitle_to_srt_into_input(
        video_fullpath, local_sub_index=(value if kind != "srt" else 0)
    )
    if srt_path:
        strip_subtitle_tags_inplace(srt_path)
        return srt_path

    print(f"[AUTO] SRT introuvable pour {video_fullpath}.")
    return None
