# add_dub/core/tts_edge.py
import io
import os
import shutil
import tempfile
import subprocess
import asyncio
from typing import Optional, List, Dict

from pydub import AudioSegment

# Même signature publique que tts.py pour rester plug-and-play
from add_dub.core.options import DubOptions
from add_dub.logger import (log_call, log_time)

# Dépendances: edge-tts + ffmpeg dans le PATH
try:
    import edge_tts
except Exception:
    edge_tts = None

# ShortName Edge par défaut (on ignore voice_id/opts dans cette version de test)
DEFAULT_EDGE_VOICE = "fr-FR-DeniseNeural"


def _require_edge_tts():
    if edge_tts is None:
        raise RuntimeError("edge-tts n'est pas installé (pip install edge-tts).")


def _speed_up_with_ffmpeg(segment: AudioSegment, factor: float) -> AudioSegment:
    """
    Accélère sans changer la hauteur avec ffmpeg (filter atempo).
    factor > 1.0 => plus rapide.
    """
    if factor <= 1.0:
        return segment
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg introuvable")

    # ffmpeg atempo accepte [0.5 .. 2.0] par maillon -> on chaîne si nécessaire
    remaining = max(1.0, min(factor, 8.0))
    filters = []
    while remaining > 2.0:
        filters.append("atempo=2.0")
        remaining /= 2.0
    filters.append(f"atempo={remaining:.6f}")
    filt = ",".join(filters)

    with tempfile.TemporaryDirectory() as td:
        inp = os.path.join(td, "in.wav")
        out = os.path.join(td, "out.wav")
        segment.export(inp, format="wav")
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", inp,
            "-filter:a", filt,
            "-vn",
            out
        ]
        subprocess.run(cmd, check=True)
        return AudioSegment.from_file(out)


def _sniff_audio_format(b: bytes) -> str:
    """
    Devine 'wav' ou 'mp3' selon les premiers octets.
    - WAV: 'RIFF' ... 'WAVE'
    - MP3: 'ID3' (tag) ou frame sync 0xFF 0xFB / 0xF3 / 0xF2
    Par défaut 'mp3' si doute (edge-tts renvoie souvent du MP3).
    """
    if len(b) >= 12 and b[0:4] == b"RIFF" and b[8:12] == b"WAVE":
        return "wav"
    if len(b) >= 3 and b[0:3] == b"ID3":
        return "mp3"
    if len(b) >= 2 and b[0] == 0xFF and b[1] in (0xFB, 0xF3, 0xF2):
        return "mp3"
    # fallback
    return "mp3"


async def _edge_synthesize_bytes_async(text: str, voice_shortname: str) -> bytes:
    """
    Synthèse Edge en flux binaire (souvent MP3 par défaut selon la version).
    On NE PASSE PAS d'output_format car ta version ne l'accepte pas.
    """
    _require_edge_tts()
    com = edge_tts.Communicate(text=text, voice=voice_shortname)
    buf = io.BytesIO()
    async for chunk in com.stream():
        if chunk["type"] == "audio":
            buf.write(chunk["data"])
    return buf.getvalue()


def _synthesize(text: str, voice_shortname: str) -> AudioSegment:
    """
    Enveloppe synchrone pratique (compatible multiprocessing).
    Détecte si MP3 ou WAV et charge avec le bon 'format'.
    """
    data = asyncio.run(_edge_synthesize_bytes_async(text, voice_shortname))
    fmt = _sniff_audio_format(data)
    return AudioSegment.from_file(io.BytesIO(data), format=fmt)



def synthesize_tts_for_subtitle(
    text: str,
    target_duration_ms: int,
    voice_id: Optional[str],   # ignoré volontairement
    opts: DubOptions,          # ignoré volontairement
) -> AudioSegment:
    """
    Version minimaliste pour test:
    - utilise toujours DEFAULT_EDGE_VOICE
    - ajuste strictement à target_duration_ms (accélération atempo si trop long, sinon padding)
    """
    if not text:
        return AudioSegment.silent(duration=max(0, target_duration_ms))

    try:
        seg = _synthesize(text, DEFAULT_EDGE_VOICE)
    except Exception as e:
        print(f"[WARN] edge-tts a échoué ({e}). Retour d'un segment silencieux.")
        return AudioSegment.silent(duration=max(0, target_duration_ms))

    tgt = max(0, int(target_duration_ms))
    cur = len(seg)

    # Accélération sans pitch shift si la synthèse dépasse la cible
    if tgt > 0 and cur > tgt:
        factor = cur / max(1, tgt)  # > 1.0
        try:
            seg = _speed_up_with_ffmpeg(seg, factor)
        except Exception as e:
            # Pas d'ffmpeg ou échec -> trim direct
            print(f"[WARN] Accélération via ffmpeg indisponible/échouée ({e}). Trim direct.")
            seg = seg[:tgt]

    # Ajustement final exact (trim / pad silence)
    cur = len(seg)
    if cur > tgt:
        seg = seg[:tgt]
    elif cur < tgt:
        seg = seg + AudioSegment.silent(duration=(tgt - cur))

    return seg


# Fonctions optionnelles pour compat (non utilisées ici)
def list_available_voices() -> List[Dict]:
    return [{"id": DEFAULT_EDGE_VOICE, "display_name": DEFAULT_EDGE_VOICE, "lang": "fr-FR"}]


def is_valid_voice_id(_voice_id: Optional[str]) -> bool:
    # On ignore les IDs fournis (souvent OneCore) dans cette version de test
    return True
