# add_dub/core/tts_edge.py
import io
import os
import shutil
import tempfile
import subprocess
import asyncio
import string
from typing import Optional, List, Dict

import add_dub.io.fs as io_fs
from pydub import AudioSegment

# Même signature publique que tts.py pour rester plug-and-play
from add_dub.core.options import DubOptions
from add_dub.logger import (log_call, log_time)

# Dépendances: edge-tts + ffmpeg dans le PATH
try:
    import edge_tts
except Exception:
    edge_tts = None

# Fallback local si aucune voix Edge n'est listable
DEFAULT_EDGE_VOICE = "fr-FR-HenriNeural"


def _require_edge_tts():
    if edge_tts is None:
        raise RuntimeError("edge-tts n'est pas installé (pip install edge-tts).")


def _normalize_voice_records(raw_voices: List[Dict]) -> List[Dict]:
    """
    Normalise la structure des voix Edge en:
      {"id": ShortName, "display_name": LocalName/Name/ShortName, "lang": Locale}
    """
    out: List[Dict] = []
    for v in raw_voices or []:
        short = (
            v.get("ShortName")
            or v.get("shortName")
            or v.get("Shortname")
            or v.get("shortname")
            or v.get("Name")  # certaines versions ne renvoient pas ShortName
        )
        if not short:
            continue
        locale = v.get("Locale") or v.get("locale") or ""
        local_name = (
            v.get("LocalName") or v.get("Localname")
            or v.get("DisplayName") or v.get("displayName")
            or v.get("Name") or short
        )
        out.append({
            "id": str(short),
            "display_name": str(local_name),
            "lang": str(locale),
        })
    return out


async def _edge_list_voices_async() -> List[Dict]:
    """
    Récupère la liste des voix Edge TTS.
    Stratégie:
      1) edge_tts.list_voices()  ← prioritaire
      2) VoicesManager.create().get_voices()  ← fallback
    """
    _require_edge_tts()

    voices: List[Dict] = []
    # 1) API directe list_voices
    try:
        if hasattr(edge_tts, "list_voices"):
            voices = await edge_tts.list_voices()  # type: ignore[attr-defined]
    except Exception:
        voices = []

    # 2) Fallback VoicesManager si nécessaire
    if not voices:
        try:
            if hasattr(edge_tts, "VoicesManager"):
                mgr = await edge_tts.VoicesManager.create()  # type: ignore[attr-defined]
                voices = await mgr.get_voices()
        except Exception:
            voices = []

    return _normalize_voice_records(voices)


def list_available_voices() -> List[Dict]:
    """
    Wrapper synchrone pour lister les voix Edge.
    """
    try:
        lst = asyncio.run(_edge_list_voices_async())
        if lst:
            return lst
    except Exception:
        pass
    # Fallback minimal si l’API a échoué
    return [{"id": DEFAULT_EDGE_VOICE, "display_name": DEFAULT_EDGE_VOICE, "lang": "fr-FR"}]


def is_valid_voice_id(voice_id: Optional[str]) -> bool:
    if not voice_id:
        return False
    try:
        s = str(voice_id).strip()
        voices = list_available_voices()
        return any(v["id"] == s for v in voices)
    except Exception:
        # En cas d'échec de listing, tolérer la voix par défaut
        return str(voice_id).strip().lower() == DEFAULT_EDGE_VOICE.lower()


def _atempo_chain_for_factor(factor: float) -> list[str]:
    """
    Construit une chaîne de filtres atempo pour couvrir un facteur arbitraire > 0
    en respectant la plage acceptée par ffmpeg (0.5..2.0 par maillon).
    """
    if factor <= 0:
        return []
    filters: list[str] = []
    remaining = factor
    while remaining < 0.5:
        filters.append("atempo=0.5")
        remaining /= 0.5
    while remaining > 2.0:
        filters.append("atempo=2.0")
        remaining /= 2.0
    if abs(remaining - 1.0) > 1e-6:
        filters.append(f"atempo={remaining:.6f}")
    return filters


def _speed_change_with_ffmpeg(segment: AudioSegment, factor: float) -> AudioSegment:
    """
    Change la vitesse (ralentit/accélère) sans changer la hauteur via ffmpeg (filter atempo).
    factor > 1.0 => plus rapide ; 0 < factor < 1.0 => plus lent.
    Si factor ~ 1.0, renvoie segment tel quel.
    """
    if factor <= 0:
        return segment
    if abs(factor - 1.0) <= 1e-6:
        return segment
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg introuvable")

    filters = _atempo_chain_for_factor(factor)
    if not filters:
        return segment
    filt = ",".join(filters)

    with tempfile.TemporaryDirectory(dir=io_fs.TMP_DIR) as td:
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
    if len(b) >= 12 and b[0:4] == b"RIFF" and b[8:12] == "WAVE".encode():
        return "wav"
    if len(b) >= 3 and b[0:3] == "ID3".encode():
        return "mp3"
    if len(b) >= 2 and b[0] == 0xFF and b[1] in (0xFB, 0xF3, 0xF2):
        return "mp3"
    return "mp3"


async def _edge_synthesize_bytes_async(text: str, voice_shortname: str) -> bytes:
    """
    Synthèse Edge en flux binaire (souvent MP3 par défaut selon la version).
    On NE PASSE PAS d'output_format pour rester compatible avec diverses versions.
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
    Écrit d'abord en fichier dans TMP_DIR pour éviter cache:pipe:0 en CWD.
    """
    data = asyncio.run(_edge_synthesize_bytes_async(text, voice_shortname))
    fmt = _sniff_audio_format(data)

    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{fmt}", dir=io_fs.TMP_DIR) as f:
        tmp_path = f.name
        f.write(data)

    try:
        seg = AudioSegment.from_file(tmp_path, format=fmt)
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass

    return seg


def _looks_like_silence(text: str) -> bool:
    """
    True si 'text' ne contient que espaces/ellipses/ponctuation/symboles.
    Ex.: "", "...", "…", ". . .", "--", "♪", "—", etc.
    """
    if text is None:
        return True

    s = str(text).strip()
    if not s:
        return True

    # Normaliser l’ellipse unicode en trois points puis retirer la ponctuation.
    s = s.replace("…", "...")
    punct = set(string.punctuation) | {"—", "–", "«", "»", "♪", "♫", "·", "•"}
    s = "".join(ch for ch in s if ch not in punct)

    # Retirer les espaces restants
    s = s.strip()

    return len(s) == 0


def synthesize_tts_for_subtitle(
    text: str,
    target_duration_ms: int,
    voice_id: Optional[str],
    opts: DubOptions,
) -> AudioSegment:
    """
    Implémentation Edge TTS avec le même comportement que gTTS côté vitesse :
    1) Synthèse (vitesse "1.0" intrinsèque Edge)
    2) Si opts.min_rate_tts != 1.0 → post-traitement atempo (vitesse minimale globale)
    3) Ajustement à target_duration_ms :
       - si trop long → accélération supplémentaire, bornée par opts.max_rate_tts
       - si trop court → padding silence
    """
    # Court-circuit SILENCE : texte vide/ellipses/ponctuation uniquement
    if _looks_like_silence(text):
        return AudioSegment.silent(duration=max(0, int(target_duration_ms)))

    shortname = voice_id if is_valid_voice_id(voice_id) else DEFAULT_EDGE_VOICE

    # Étape 1 — synthèse (protégée)
    try:
        seg = _synthesize(text, shortname)
    except Exception:
        # Sécurité : si Edge échoue (ex. NoAudioReceived), renvoyer du silence
        return AudioSegment.silent(duration=max(0, int(target_duration_ms)))

    # Étape 2 — vitesse minimale pilotée (post-traitement)
    try:
        base_rate = float(getattr(opts, "min_rate_tts", 1.0) or 1.0)
    except Exception:
        base_rate = 1.0

    if base_rate > 0 and abs(base_rate - 1.0) > 1e-6:
        try:
            seg = _speed_change_with_ffmpeg(seg, base_rate)
        except Exception:
            # Continuer avec la synthèse brute si atempo échoue
            pass

    # Étape 3 — ajustement à la durée cible
    tgt = max(0, int(target_duration_ms))
    cur = len(seg)

    if tgt > 0 and cur > tgt:
        # facteur d'accélération requis
        needed_factor = cur / max(1, tgt)  # > 1.0
        # plafond via max_rate_tts (par défaut 1.8 si non renseigné)
        try:
            max_rate = float(getattr(opts, "max_rate_tts", 1.8) or 1.8)
        except Exception:
            max_rate = 1.8
        if max_rate < 1.0:
            max_rate = 1.0  # sécurité: pas de plafond < 1 pour accélérer
        
        factor = min(needed_factor, max_rate)

        try:
            sped = _speed_change_with_ffmpeg(seg, factor)
            # Ajustement final exact
            if len(sped) > tgt:
                seg = sped[:tgt]
            else:
                seg = sped + AudioSegment.silent(duration=(tgt - len(sped)))
        except Exception:
            # Pas d'ffmpeg ou échec → trim direct
            seg = seg[:tgt]
    else:
        # Padding si trop court
        if cur < tgt:
            seg = seg + AudioSegment.silent(duration=(tgt - cur))

    return seg
