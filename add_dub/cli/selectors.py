# add_dub/cli/selectors.py
import os
import sys
import add_dub.io.fs as io_fs
from add_dub.adapters.ffmpeg import get_track_info
from add_dub.adapters.mkvtoolnix import list_mkv_sub_tracks
from add_dub.core.subtitles import find_sidecar_srt
from add_dub.logger import logger as log

from add_dub.i18n import t

# ... imports ...

def choose_files(files):
    if not files:
        print(t("cli_no_eligible", path="input/"))
        return None

    while True:
        print(t("cli_files_list"))
        for idx, f in enumerate(files, start=1):
            print(f"    {idx}. {f}")

        sel = input(t("cli_select_files")).strip().lower()

        if sel == "":
            return files
        if sel == "q":
            print(t("cli_selection_cancelled"))
            return None

        parts = sel.split()
        indices = []
        ok = True

        for p in parts:
            if not p.isdigit():
                ok = False
                break
            i = int(p)
            if i < 1 or i > len(files):
                ok = False
                break
            indices.append(i)

        if not ok or not indices:
            print(t("cli_invalid_selection", max=len(files)))
            continue

        seen = set()
        selected = []
        for i in indices:
            if i not in seen:
                seen.add(i)
                selected.append(files[i - 1])

        return selected


def choose_audio_track_ffmpeg_index(video_fullpath):
    tracks = get_track_info(video_fullpath)
    if not tracks:
        log.error("Aucune piste audio trouvée pour %s", video_fullpath)
        return None

    print(t("cli_audio_tracks"))
    for idx, stream in enumerate(tracks):
        ff_idx = stream.get("index")
        tags = stream.get("tags", {}) or {}
        lang = tags.get("language", "und")
        title = tags.get("title", "")
        print(t("cli_track_info", idx=idx, ff_idx=ff_idx, lang=lang, title=title))

    while True:
        chosen = input(t("cli_choose_track")).strip().lower()
        if chosen == "":
            return tracks[0].get("index")
        if chosen == "q":
            print(t("cli_track_cancelled"))
            return None
        if chosen.isdigit():
            chosen_idx = int(chosen)
            if 0 <= chosen_idx < len(tracks):
                return tracks[chosen_idx].get("index")
        print(t("cli_invalid_track", max=len(tracks) - 1))


def choose_subtitle_source(video_fullpath):
    """
    Retourne:
        ("srt", srt_path)  ou  ("mkv", local_sub_index)

    Règles:
      - Si un SRT homonyme existe dans srt/ → on l'affiche et on LE PRIVILÉGIE.
      - Sinon, si un sidecar .srt est à côté de la vidéo → on l'affiche.
      - Les pistes MKV sont toujours listées derrière.
      - Si SRT dans srt/ ET sidecar existent, on n'affiche QUE celui de srt/.
    """
    base_name = os.path.splitext(os.path.basename(video_fullpath))[0]
    srt_in_srt = io_fs.join_srt(base_name + ".srt")
    has_srt_in_srt = os.path.exists(srt_in_srt)

    sidecar = find_sidecar_srt(video_fullpath)

    choices = []
    labels = []

    # 1) SRT dans srt/ prioritaire (et exclusif vis-à-vis du sidecar)
    if has_srt_in_srt:
        choices.append(("srt", srt_in_srt))
        labels.append(f"    0 : SRT (srt/) -> {os.path.basename(srt_in_srt)}")
    # 2) Sinon, proposer le sidecar s'il existe
    elif sidecar:
        choices.append(("srt", sidecar))
        labels.append(f"    0 : SRT sidecar -> {os.path.basename(sidecar)}")

    # 3) Pistes MKV (le cas échéant)
    _, ext = os.path.splitext(video_fullpath)
    if ext.lower().endswith(".mkv"):
        tracks, printable = list_mkv_sub_tracks(video_fullpath)
        for i, _t in enumerate(tracks):
            local_idx = i
            labels.append(f"    {len(choices)} : {printable[i]}")
            choices.append(("mkv", local_idx))

    if not choices:
        print(t("cli_no_subs"))
        return None

    print(t("cli_subs_sources"))
    for line in labels:
        print(line)

    s = input(t("cli_choose_sub", max=len(choices)-1)).strip()
    try:
        idx = int(s) if s != "" else 0
    except Exception:
        idx = 0
    if idx < 0 or idx >= len(choices):
        idx = 0
    return choices[idx]
