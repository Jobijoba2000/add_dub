# add_dub/cli/args.py
from __future__ import annotations

import argparse
import re
from typing import Tuple, List

from add_dub.config.effective import effective_values


def parse_args(argv: List[str]) -> Tuple[argparse.Namespace, List[str]]:
    """
    Les defaults d'argparse viennent du builder partagé (options.conf > defaults.py).
    Si l'utilisateur ne passe pas un flag, il récupère ces valeurs "effectives".
    """
    fused = effective_values()

    parser = argparse.ArgumentParser(
        prog="add_dub",
        description="AdDub — Ajout de doublage TTS sur vidéos."
    )

    # Modes
    g_mode = parser.add_mutually_exclusive_group()
    g_mode.add_argument("--interactive", action="store_true", help="Lance l'interface interactive (défaut).")
    g_mode.add_argument("--batch", action="store_true", help="Traite sans interaction.")

    # Actions utilitaires
    parser.add_argument("--list-voices", action="store_true", help="Affiche les voix disponibles et quitte.")

    # Cibles (batch)
    parser.add_argument("--input", "-i", nargs="+", metavar="PATH",
                        help="Fichiers vidéo ou dossiers à traiter. En dossier: parcourt les vidéos détectables.")
    parser.add_argument("--recursive", "-r", action="store_true", help="Parcourt les dossiers récursivement (batch).")

    # Sélection technique
    parser.add_argument("--tts-engine",
                        choices=["onecore", "edge", "gtts"],
                        default=fused["tts_engine"],
                        help="Moteur TTS à utiliser (par défaut: options.conf → effective).")
    parser.add_argument("--audio-index", type=int, default=None,
                        help="Index global FFmpeg de la piste audio source (ffprobe->streams[index]).")
    parser.add_argument("--voice", metavar="VOICE_ID", default=fused["voice"],
                        help="Identifiant de la voix TTS à utiliser (optionnel).")

    # Sous-titres — un seul argument: auto (défaut), srt, mkv, mkv:N
    parser.add_argument("--sub",
                        default="auto",
                        help="Source des sous-titres: auto (défaut), srt, mkv, mkv:N (ex. mkv:4).")

    # Mixages / niveaux / calages — defaults issus de la fusion conf→defaults
    parser.add_argument("--offset-ms", type=int, default=fused["offset_ms"],
                        help="Décalage global des sous-titres/voix (ms).")
    parser.add_argument("--offset-video-ms", type=int, default=fused["offset_video_ms"],
                        help="Décalage de la vidéo (ms) appliqué dans le mux final.")
    parser.add_argument("--ducking-db", type=float, default=fused["ducking_db"],
                        help="Réduction du fond (dB) pendant la voix (ducking).")
    parser.add_argument("--bg-mix", type=float, default=fused["bg_mix"],
                        help="Gain de la piste 'fond' (après aformat/resample), multiplicatif.")
    parser.add_argument("--tts-mix", type=float, default=fused["tts_mix"],
                        help="Gain de la piste 'tts' (après aformat/resample), multiplicatif.")
    parser.add_argument("--min-rate-tts", type=float, default=fused["min_rate_tts"],
                        help="Vitesse minimale de lecture TTS (facteur).")
    parser.add_argument("--max-rate-tts", type=float, default=fused["max_rate_tts"],
                        help="Vitesse maximale de lecture TTS (facteur).")

    # Codecs / sortie
    parser.add_argument("--audio-codec", default=fused["audio_codec"],
                        choices=["ac3", "aac", "libopus", "opus", "flac", "libvorbis", "vorbis", "pcm_s16le"],
                        help="Codec audio cible pour la piste doublage+original.")
    parser.add_argument("--audio-bitrate", type=int, default=fused["audio_bitrate"],
                        help="Bitrate audio (kb/s) pour le codec cible (si pertinent).")
    parser.add_argument("--output-dir", default=None, metavar="PATH",
                        help="Dossier de sortie (défaut: ./output).")

    # Flags booléens (inchangés)
    parser.add_argument("--overwrite", action="store_true", help="Écrase les sorties existantes si présent.")
    parser.add_argument("--dry-run", action="store_true", help="Montre ce qui serait fait sans écrire les fichiers.")
    parser.add_argument("--limit-duration-sec", type=int, default=None,
                        help="Limite la durée traitée (tests rapides).")

    args, unknown = parser.parse_known_args(argv)

    # Normalisation de --sub en sub_mode + sub_index
    raw = (getattr(args, "sub", "auto") or "auto").strip().lower()
    sub_mode = "auto"
    sub_index = 0
    m = re.match(r"^(mkv)\s*[:=]\s*(\d+)$", raw)
    if m:
        sub_mode = "mkv"
        sub_index = int(m.group(2))
    elif raw in ("auto", "srt", "mkv"):
        sub_mode = raw
    else:
        sub_mode = "auto"
        sub_index = 0

    args.sub_mode = sub_mode
    args.sub_index = sub_index

    return args, unknown


def want_interactive(args: argparse.Namespace) -> bool:
    """
    Décide si on doit lancer l'interactif.
    - Interactif si --interactive
    - Interactif si rien n'est précisé
    - Batch si --batch
    """
    if getattr(args, "batch", False):
        return False
    return True
