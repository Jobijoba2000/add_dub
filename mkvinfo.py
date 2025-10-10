#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

# Chemins par défaut : outils à côté du script
DEFAULT_TOOLS_DIR = (Path(__file__).parent / "tools" / "MKVToolNix").resolve()
DEFAULT_MKVMERGE = (DEFAULT_TOOLS_DIR / "mkvmerge.exe").resolve()
DEFAULT_MKVINFO  = (DEFAULT_TOOLS_DIR / "mkvinfo.exe").resolve()
DEFAULT_MKVEXTRACT = (DEFAULT_TOOLS_DIR / "mkvextract.exe").resolve()

def run(cmd):
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "Commande échouée.")
    return proc.stdout

def ensure_exists(path: Path, label: str):
    if not path.exists():
        print(f"{label} introuvable : {path}")
        sys.exit(1)

def list_mkvs(directory: Path):
    return sorted([p for p in directory.glob("*.mkv") if p.is_file()])

def choose_index(n):
    while True:
        try:
            s = input(f"Saisis un numéro entre 1 et {n} : ").strip()
            idx = int(s)
            if 1 <= idx <= n:
                return idx - 1
            print("Numéro invalide.")
        except ValueError:
            print("Merci d’entrer un nombre valide.")

def first_timecode_ms_with_mkvextract(mkvextract: Path, file_path: Path, track_id: int) -> float:
    """
    Retourne le premier timecode (en ms) de la piste TID en utilisant:
        mkvextract timecodes_v2 "file.mkv" TID:out.txt
    On lit la première ligne numérique (en ms). Format: entête en commentaires + une valeur par ligne.
    """
    with tempfile.TemporaryDirectory() as td:
        out_path = Path(td) / f"timecodes_track_{track_id}.txt"
        # Extrait la liste complète (rapide en général, mais peut prendre un peu sur de gros fichiers)
        run([str(mkvextract), "timecodes_v2", str(file_path), f"{track_id}:{out_path}"])
        first_val = None
        with out_path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # Les timecodes_v2 sont en ms, décimaux possibles
                try:
                    first_val = float(line)
                    break
                except ValueError:
                    continue
        if first_val is None:
            # Si aucune valeur, on considère 0.0 (piste vide/inconnue)
            first_val = 0.0
        return first_val

def try_delay_from_mkvmerge_json(mkvmerge: Path, file_path: Path):
    """
    Tente de lire un décalage directement dans le JSON de mkvmerge (-J).
    Peu de fichiers stockent un 'offset' explicite ; on renvoie un dict {track_id: offset_ms} si trouvé.
    """
    data = json.loads(run([str(mkvmerge), "-J", str(file_path)]))
    delays = {}
    for t in data.get("tracks", []):
        tid = t.get("id")
        props = t.get("properties", {}) or {}
        # Champs possibles selon les cas : 'timestamp_offset' (ms), 'codec_delay' (ns), etc.
        if "timestamp_offset" in props:
            # timestamp_offset est en ms (entier)
            delays[tid] = float(props["timestamp_offset"])
        elif "codec_delay" in props:
            # codec_delay est en ns -> ms
            delays[tid] = float(props["codec_delay"]) / 1_000_000.0
        # D’autres champs existent (seek_pre_roll ns) mais ce n’est pas un décalage de calage “éditorial”
    return delays

def main():
    parser = argparse.ArgumentParser(description="Affiche le calage (décalage) des pistes en ms d’un MKV (via MKVToolNix).")
    parser.add_argument("-d", "--dir", default="input", help="Répertoire des MKV (défaut: input)")
    parser.add_argument("--tools-dir", type=Path, default=DEFAULT_TOOLS_DIR, help=f"Dossier MKVToolNix (défaut: {DEFAULT_TOOLS_DIR})")
    parser.add_argument("--mkvmerge", type=Path, default=None, help="Chemin vers mkvmerge.exe")
    parser.add_argument("--mkvinfo", type=Path, default=None, help="Chemin vers mkvinfo.exe (optionnel)")
    parser.add_argument("--mkvextract", type=Path, default=None, help="Chemin vers mkvextract.exe")
    parser.add_argument("--fullscan", action="store_true",
                        help="Ignore les métadonnées de décalage et mesure toujours via timecodes_v2 (plus fiable).")
    args = parser.parse_args()

    tools_dir = args.tools_dir.resolve()
    mkvmerge = (args.mkvmerge.resolve() if args.mkvmerge else (tools_dir / "mkvmerge.exe").resolve())
    mkvinfo = (args.mkvinfo.resolve() if args.mkvinfo else (tools_dir / "mkvinfo.exe").resolve())
    mkvextract = (args.mkvextract.resolve() if args.mkvextract else (tools_dir / "mkvextract.exe").resolve())

    print(f"Outils MKVToolNix : {tools_dir}")
    print(f"mkvmerge  : {mkvmerge}")
    print(f"mkvinfo   : {mkvinfo}")
    print(f"mkvextract: {mkvextract}")

    ensure_exists(mkvmerge, "mkvmerge")
    ensure_exists(mkvextract, "mkvextract")

    directory = Path(args.dir).expanduser().resolve()
    if not directory.exists() or not directory.is_dir():
        print(f"Le répertoire n’existe pas : {directory}")
        sys.exit(1)

    mkvs = list_mkvs(directory)
    if not mkvs:
        print(f"Aucun .mkv trouvé dans : {directory}")
        sys.exit(0)

    print(f"\nMKV trouvés dans {directory} :")
    for i, p in enumerate(mkvs, start=1):
        print(f"  {i}. {p.name}")

    if len(mkvs) == 1:
        choice = 0
        print("\nUn seul fichier trouvé, sélection automatique.")
    else:
        print()
        choice = choose_index(len(mkvs))

    file_path = mkvs[choice]
    print(f"\nFichier choisi : {file_path.name}")

    # 1) Identification des pistes (id, type, nom)
    ident_json = json.loads(run([str(mkvmerge), "-J", str(file_path)]))
    tracks = []
    for t in ident_json.get("tracks", []):
        tracks.append({
            "id": t.get("id"),
            "type": t.get("type"),
            "codec": t.get("codec"),
            "language": (t.get("properties") or {}).get("language", "und"),
            "name": (t.get("properties") or {}).get("track_name", "")
        })

    # 2) Tentative: décalage direct du conteneur (rare)
    container_delays_ms = {} if args.fullscan else try_delay_from_mkvmerge_json(mkvmerge, file_path)

    # 3) Mesure de début réel par piste via timecodes_v2 (fiable)
    # On prendra la vidéo de plus petit ID comme référence “0 ms”.
    video_ids = [t["id"] for t in tracks if t["type"] == "video"]
    if not video_ids:
        print("Aucune piste vidéo détectée — calage relatif à la première piste trouvée.")
        ref_id = tracks[0]["id"]
    else:
        ref_id = min(video_ids)

    first_times_ms = {}
    for t in tracks:
        tid = t["id"]
        try:
            first_ms = first_timecode_ms_with_mkvextract(mkvextract, file_path, tid)
        except RuntimeError as e:
            print(f"Échec lecture timecodes piste {tid}: {e}")
            first_ms = 0.0
        first_times_ms[tid] = first_ms

    ref_start = first_times_ms.get(ref_id, 0.0)

    # 4) Calage final : priorité à la mesure réelle ; on montre aussi l’info conteneur si dispo
    print("\n=== Calage des pistes (ms) ===")
    print(f"(Référence: vidéo ID {ref_id} à 0 ms)")
    print(f"{'ID':>3}  {'Type':8}  {'Lang':5}  {'Codec':12}  {'Nom':25}  {'Début réel':>11}  {'Décalage vs vidéo':>18}  {'Meta delay?':>11}")
    for t in tracks:
        tid = t["id"]
        start_ms = first_times_ms.get(tid, 0.0)
        rel_ms = start_ms - ref_start
        meta = container_delays_ms.get(tid)
        name = (t["name"] or "")[:25]
        print(f"{tid:>3}  {t['type']:8}  {t['language'][:5]:5}  {str(t['codec'])[:12]:12}  {name:25}  {start_ms:11.3f}  {rel_ms:18.3f}  {('' if meta is None else f'{meta:.3f}') :>11}")

    print("\nInterprétation :")
    print("- 'Début réel' = premier timecode de la piste (ms) tel qu’encodé.")
    print("- 'Décalage vs vidéo' = (début piste) - (début de la vidéo). Positif : piste commence après la vidéo.")
    print("- 'Meta delay?' affiche un éventuel décalage stocké dans les métadonnées (rare).")

if __name__ == "__main__":
    main()
