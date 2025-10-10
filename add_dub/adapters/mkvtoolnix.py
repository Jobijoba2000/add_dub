# add_dub/adapters/mkvtoolnix.py
import os
import shutil
import json
import subprocess
import tempfile
from pathlib import Path

def _find_exe(candidates):
    for c in candidates:
        p = shutil.which(c)
        if p:
            return p
        if os.path.exists(c):
            return c
    return None

def mkvmerge_identify_json(video_path):
    mkvmerge = _find_exe([
        "mkvmerge",
        r"C:\Program Files\MKVToolNix\mkvmerge.exe",
        r"C:\Program Files (x86)\MKVToolNix\mkvmerge.exe",
    ])
    if not mkvmerge:
        return None
    try:
        r = subprocess.run([mkvmerge, "-J", video_path],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return json.loads(r.stdout)
    except Exception:
        return None

def mkv_has_subtitle_track(video_path):
    info = mkvmerge_identify_json(video_path)
    if not info:
        return False
    for t in info.get("tracks", []):
        if t.get("type") == "subtitles":
            return True
    return False

def list_mkv_sub_tracks(video_path):
    info = mkvmerge_identify_json(video_path)
    tracks = []
    printable = []
    if not info:
        return tracks, printable
    for t in info.get("tracks", []):
        if t.get("type") == "subtitles":
            tid = t.get("id")
            prop = t.get("properties", {}) or {}
            cid = (prop.get("codec_id") or "").lower()
            lang = prop.get("language", "und")
            name = prop.get("track_name", "")
            tracks.append(t)
            printable.append(f"  mkv id={tid} | codec={cid} | lang={lang} | title={name}")
    return tracks, printable



def audio_video_offset_ms(video_path, audio_track_id):
    """
    Renvoie le décalage en millisecondes entre la piste audio spécifiée
    et la première piste vidéo du fichier :
        offset = audio_start - video_start

    Retourne un int (ms). Positif = audio commence après la vidéo.
    """
    mkvmerge = _find_exe([
        "mkvmerge",
        r"C:\Program Files\MKVToolNix\mkvmerge.exe",
        r"C:\Program Files (x86)\MKVToolNix\mkvmerge.exe",
    ])
    mkvextract = _find_exe([
        "mkvextract",
        r"C:\Program Files\MKVToolNix\mkvextract.exe",
        r"C:\Program Files (x86)\MKVToolNix\mkvextract.exe",
    ])
    if not mkvmerge or not mkvextract:
        raise FileNotFoundError("mkvmerge ou mkvextract introuvable")

    # Obtenir l'ID de la piste vidéo de référence
    result = subprocess.run([mkvmerge, "-J", video_path],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
    info = json.loads(result.stdout)
    video_ids = sorted(t["id"] for t in info.get("tracks", []) if t.get("type") == "video")
    if not video_ids:
        raise RuntimeError("Aucune piste vidéo trouvée")
    video_id = video_ids[0]

    def first_timecode(track_id):
        with tempfile.TemporaryDirectory() as td:
            out_file = Path(td) / f"timecodes_{track_id}.txt"
            r = subprocess.run(
                [mkvextract, "timecodes_v2", video_path, f"{track_id}:{out_file}"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            if r.returncode != 0:
                raise RuntimeError(r.stderr.strip())
            with out_file.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    return float(line)
        return 0.0

    video_start = first_timecode(video_id)
    audio_start = first_timecode(audio_track_id)

    return int(round(audio_start - video_start))
