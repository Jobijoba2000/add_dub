# add_dub/cli/selectors.py
import os
import sys
import add_dub.io.fs as io_fs
from add_dub.adapters.ffmpeg import get_track_info
from add_dub.adapters.mkvtoolnix import list_mkv_sub_tracks
from add_dub.core.subtitles import find_sidecar_srt
from add_dub.logger import logger as log

def choose_files(files):
    if not files:
        print("Aucun fichier éligible trouvé dans input/.")
        return None

    while True:
        print("\nFichiers éligibles (input/):")
        for idx, f in enumerate(files, start=1):
            print(f"    {idx}. {f}")

        sel = input("Entrez les numéros à traiter (espaces, Entrée=tout, q=annuler) : ").strip().lower()

        if sel == "":
            return files
        if sel == "q":
            print("Aucun fichier sélectionné.")
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
            print("Saisie invalide. Exemple : 1 3 5 (dans l’intervalle 1..%d)." % len(files))
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

    print("\nPistes audio disponibles :")
    for idx, stream in enumerate(tracks):
        ff_idx = stream.get("index")
        tags = stream.get("tags", {}) or {}
        lang = tags.get("language", "und")
        title = tags.get("title", "")
        print(f"    {idx} : ffmpeg index {ff_idx}, langue={lang}, titre={title}")

    while True:
        chosen = input("Numéro de la piste audio à utiliser (Entrée=0, q=annuler) : ").strip().lower()
        if chosen == "":
            return tracks[0].get("index")
        if chosen == "q":
            print("Sélection de piste annulée.")
            return None
        if chosen.isdigit():
            chosen_idx = int(chosen)
            if 0 <= chosen_idx < len(tracks):
                return tracks[chosen_idx].get("index")
        print(f"Saisie invalide. Choisis un nombre entre 0 et {len(tracks) - 1}, ou q pour annuler.")


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
        print("Aucune source de sous-titres disponible.")
        return None

    print("\nSources de sous-titres :")
    for line in labels:
        print(line)

    s = input(f"Choisir la source ST (0..{len(choices)-1}) [0]: ").strip()
    try:
        idx = int(s) if s != "" else 0
    except Exception:
        idx = 0
    if idx < 0 or idx >= len(choices):
        idx = 0
    return choices[idx]
