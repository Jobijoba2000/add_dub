# add_dub/adapters/mkvtoolnix.py
import os
import shutil
import json
import subprocess

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
