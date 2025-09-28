# add_dub/core/subtitles.py
import os
import re
import html
import time
import shutil
import subprocess
import tempfile

from add_dub.io.fs import INPUT_DIR, join_input as _join_input
from add_dub.adapters.mkvtoolnix import mkv_has_subtitle_track, mkvmerge_identify_json
from add_dub.adapters.subtitle_edit import subtitle_edit_ocr, vobsub2srt_ocr


def _find_exe(candidates):
    """
    Retourne le premier exécutable existant parmi la liste.
    Essaie d'abord le PATH via shutil.which, puis teste l'existence.
    """
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
                t = re.sub(r"<[^>]+>", "", t)            # balises HTML
                t = re.sub(r"\{\\[^}]*\}", "", t)        # tags ASS {\...}
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
    Retourne les fichiers éligibles situés dans input/ :
    - MKV : affiché si au moins une piste ST intégrée OU SRT sidecar présent.
    - MP4 : affiché seulement si SRT sidecar présent.
    """
    try:
        files = os.listdir(INPUT_DIR)
    except FileNotFoundError:
        files = []
    candidates = []
    for f in files:
        full = _join_input(f)
        if not os.path.isfile(full):
            continue
        fl = f.lower()
        if fl.endswith(".mkv"):
            srt = find_sidecar_srt(full)
            if srt or mkv_has_subtitle_track(full):
                candidates.append(f)
        elif fl.endswith(".mp4"):
            srt = find_sidecar_srt(full)
            if srt:
                candidates.append(f)
        elif fl.endswith(".avi"):
            srt = find_sidecar_srt(full)
            if srt:
                candidates.append(f)
    return sorted(candidates, key=lambda x: x.lower())


def extract_first_subtitle_to_srt_into_input(
    video_fullpath: str, local_sub_index: int = 0, ocr_lang: str = "fr"
) -> str | None:
    """
    Extrait une piste ST du MKV en SRT et l'écrit dans input/ sous le même nom que la vidéo.
    Retourne le chemin du SRT ou None.
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
    target_srt = _join_input(base + ".srt")

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

    # Pistes image -> extraction binaire + OCR
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

        # extraction de la piste image
        cmd = ["mkvextract", "tracks", video_fullpath, f"{track_id}:{ocr_input}"]
        # si mkvextract n'est pas dans PATH, utilise le chemin absolu trouvé
        if os.path.basename(mkvextract).lower() != "mkvextract":
            cmd[0] = mkvextract
        subprocess.run(
            cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )

        # --- OCR via adapters ---
        tmp_out = os.path.join(tmp_dir, base + ".srt")

        # 1) Subtitle Edit
        ok = subtitle_edit_ocr(ocr_input, tmp_out, cwd=tmp_dir)
        if ok:
            os.replace(tmp_out, target_srt)
            strip_subtitle_tags_inplace(target_srt)
            print(f"SRT OCR (Subtitle Edit) -> {target_srt}")
            return target_srt

        # 2) vobsub2srt seulement pour .sub
        if ext == ".sub":
            produced = vobsub2srt_ocr(base_noext, lang=ocr_lang, cwd=tmp_dir)
            if produced:
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
    Détermine le SRT à utiliser pour une vidéo donnée en mode AUTO.
    - ("srt", path) : on attend un sidecar SRT présent à côté de chaque vidéo.
    - ("mkv", idx)  : on extrait systématiquement cette piste vers input/.
    """
    kind, value = sub_choice_global
    if kind == "srt":
        srt_path = find_sidecar_srt(video_fullpath)
        if srt_path:
            strip_subtitle_tags_inplace(srt_path)
            return srt_path
        else:
            print(f"[AUTO] SRT manquant pour {video_fullpath}.")
            return None
    else:
        # Extraction à partir de la piste MKV (index local 'value')
        return extract_first_subtitle_to_srt_into_input(
            video_fullpath, local_sub_index=value
        )
