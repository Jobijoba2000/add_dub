# add_dub/core/tts_gtts.py
import os
import shutil
import tempfile
import subprocess
from typing import Optional, List, Dict

import add_dub.io.fs as io_fs
from pydub import AudioSegment

# Même signature publique que tts.py / tts_edge.py
from add_dub.core.options import DubOptions

# Dépendances: gTTS + ffmpeg dans le PATH (pour atempo si besoin)
try:
    from gtts import gTTS
    from gtts.lang import tts_langs
except Exception:
    gTTS = None
    tts_langs = None


def _require_gtts():
    if gTTS is None or tts_langs is None:
        raise RuntimeError("gTTS n'est pas installé (pip install gTTS).")


def list_available_voices() -> List[Dict]:
    """
    gTTS n'a pas de “voix” multiples par langue; on modélise chaque langue comme une “voix”.
    id = code langue (ex. 'fr'), display_name = nom de langue, lang = code (même valeur)
    """
    _require_gtts()
    langs = tts_langs()  # dict { code: label }
    out: List[Dict] = []
    for code, label in sorted(langs.items(), key=lambda kv: kv[0]):
        out.append({
            "id": code,
            "display_name": label,
            "lang": code,  # on réutilise le code comme "locale"
        })
    return out


def is_valid_voice_id(voice_id: Optional[str]) -> bool:
    _require_gtts()
    if not voice_id:
        return False
    code = str(voice_id).strip().lower()
    langs = tts_langs()
    return code in langs


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
    Si factor ~ 1.0, renvoie segment.
    """
    if factor <= 0:
        return segment
    if abs(factor - 1.0) <= 1e-6:
        return segment
    if shutil.which("ffmpeg") is None:
        return segment

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


def _synthesize_to_audiosegment(text: str, lang_code: str) -> AudioSegment:
    """
    gTTS génère du MP3; on écrit d'abord un fichier dans le tmp configuré,
    puis on charge par chemin (évite le cache:pipe:0 de ffmpeg dans le CWD).
    """
    _require_gtts()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3", dir=io_fs.TMP_DIR) as f:
        tmp_path = f.name
        tts = gTTS(text=text, lang=lang_code, slow=False)
        tts.write_to_fp(f)

    try:
        seg = AudioSegment.from_file(tmp_path, format="mp3")
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass

    return seg


def synthesize_tts_for_subtitle(
    text: str,
    target_duration_ms: int,
    voice_id: Optional[str],   # ici: code langue gTTS (ex. 'fr')
    opts: DubOptions,
) -> AudioSegment:
    """
    Implémentation gTTS avec pilotage de vitesse:
    1) Synthèse (vitesse "1.0" intrinsèque gTTS)
    2) Si opts.min_rate_tts != 1.0 → post-traitement atempo (vitesse minimale globale)
    3) Ajustement à target_duration_ms:
       - si trop long → accélération supplémentaire, **bornée par opts.max_rate_tts**
       - si trop court → padding silence
    """
    if not text:
        return AudioSegment.silent(duration=max(0, target_duration_ms))

    if not is_valid_voice_id(voice_id):
        raise ValueError(f"Voice/lang gTTS invalide: {voice_id!r}")

    # Étape 1 — synthèse
    seg = _synthesize_to_audiosegment(text, str(voice_id).strip().lower())

    # Étape 2 — vitesse minimale pilotée (post-traitement)
    try:
        base_rate = float(getattr(opts, "min_rate_tts", 1.0) or 1.0)
    except Exception:
        base_rate = 1.0

    if base_rate > 0 and abs(base_rate - 1.0) > 1e-6:
        try:
            seg = _speed_change_with_ffmpeg(seg, base_rate)
        except Exception:
            pass  # on continue avec la synthèse brute si échec

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
            max_rate = 1.0  # sécurité: un plafond < 1 n'a pas de sens pour accélérer

        factor = min(needed_factor, max_rate)

        try:
            sped = _speed_change_with_ffmpeg(seg, factor)
            # Ajustement final
            if len(sped) > tgt:
                seg = sped[:tgt]
            else:
                seg = sped + AudioSegment.silent(duration=(tgt - len(sped)))
        except Exception:
            # Pas d'ffmpeg ou échec → trim direct à la durée cible
            seg = seg[:tgt]
    else:
        # Padding si trop court
        if cur < tgt:
            seg = seg + AudioSegment.silent(duration=(tgt - cur))

    return seg
