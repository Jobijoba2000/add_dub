# add_dub/cli/selectors.py
import os
import sys
import add_dub.io.fs as io_fs
from add_dub.adapters.ffmpeg import get_track_info
from add_dub.adapters.mkvtoolnix import list_mkv_sub_tracks
from add_dub.core.subtitles import find_sidecar_srt


def choose_files(files):
    if not files:
        print("Aucun fichier éligible trouvé dans input/.")
        sys.exit(1)
    print("\nFichiers éligibles (input/):")
    for idx, f in enumerate(files, start=1):
        print(f"    {idx}. {f}")
    sel = input("Entrez les numéros à traiter (espaces, Entrée=tout) : ").strip()
    if sel == "":
        return files
    try:
        indices = [int(x) for x in sel.split() if x.isdigit() and 1 <= int(x) <= len(files)]
        return [files[i - 1] for i in indices]
    except Exception:
        print("Sélection invalide. Traitement de tous les fichiers.")
        return files


def choose_audio_track_ffmpeg_index(video_fullpath):
    tracks = get_track_info(video_fullpath)
    if not tracks:
        print("Aucune piste audio trouvée.")
        sys.exit(1)
    print("\nPistes audio disponibles :")
    for idx, stream in enumerate(tracks, start=0):
        index = stream.get("index")
        tags = stream.get("tags", {}) or {}
        lang = tags.get("language", "und")
        title = tags.get("title", "")
        print(f"    {idx} : ffmpeg index {index}, langue={lang}, titre={title}")
    chosen = input("Numéro de la piste audio à utiliser (défaut 0) : ").strip()
    try:
        chosen_idx = int(chosen) if chosen != "" else 0
        if chosen_idx < 0 or chosen_idx >= len(tracks):
            raise Exception("Numéro invalide")
    except Exception:
        print("Sélection invalide. Fin du programme.")
        sys.exit(1)
    return tracks[chosen_idx].get("index")


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
