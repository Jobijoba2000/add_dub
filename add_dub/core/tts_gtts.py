# add_dub/core/tts_gtts.py
import io
import os
import shutil
import tempfile
import subprocess
import string
from typing import Optional, List, Dict

import add_dub.io.fs as io_fs
from pydub import AudioSegment

# Même signature publique que tts.py / tts_edge.py pour rester plug-and-play
from add_dub.core.options import DubOptions

# Dépendances: gTTS + ffmpeg dans le PATH
try:
    from gtts import gTTS  # type: ignore
    try:
        # gTTS >=2.5: expose tts_langs(); sinon on tombera sur le fallback
        from gtts.lang import tts_langs  # type: ignore
    except Exception:  # pragma: no cover
        tts_langs = None  # type: ignore
except Exception:  # pragma: no cover
    gTTS = None  # type: ignore
    tts_langs = None  # type: ignore

# Valeurs par défaut pour gTTS
DEFAULT_GTTS_LANG = "fr"
DEFAULT_GTTS_TLD = "com"


def _require_gtts():
    if gTTS is None:
        raise RuntimeError("gTTS n'est pas installé (pip install gTTS).")


# -------------------------------------------------------------------
# Exigé par tts_registry.py
# -------------------------------------------------------------------
def list_available_voices() -> List[Dict]:
    """
    Retourne la liste des 'voix' gTTS. gTTS ne gère pas de timbres/voix différentes,
    uniquement des langues. On expose donc (id=code_lang, display_name, lang).
    """
    # Essai dynamique si la lib le permet
    if tts_langs is not None:
        try:
            langs: Dict[str, str] = tts_langs()  # ex: {"fr": "French", "en": "English", ...}
            out = []
            for code, name in sorted(langs.items(), key=lambda kv: kv[0].lower()):
                out.append({"id": code, "display_name": f"{name} (gTTS)", "lang": code})
            if out:
                return out
        except Exception:
            pass

    # Fallback minimal si indisponible
    return [
        {"id": "fr", "display_name": "French (gTTS)", "lang": "fr"},
        {"id": "en", "display_name": "English (gTTS)", "lang": "en"},
        {"id": "es", "display_name": "Spanish (gTTS)", "lang": "es"},
        {"id": "de", "display_name": "German (gTTS)", "lang": "de"},
        {"id": "it", "display_name": "Italian (gTTS)", "lang": "it"},
        {"id": "pt", "display_name": "Portuguese (gTTS)", "lang": "pt"},
    ]


def is_valid_voice_id(voice_id: Optional[str]) -> bool:
    """
    Valide que 'voice_id' est un code de langue gTTS supporté (ex. 'fr', 'en', ...).
    """
    if not voice_id:
        return False
    vid = str(voice_id).strip().lower()
    try:
        return any(v["id"].lower() == vid for v in list_available_voices())
    except Exception:
        return vid in (DEFAULT_GTTS_LANG,)


# -------------------------------------------------------------------
# Outils audio
# -------------------------------------------------------------------
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

    # Normaliser l’ellipse unicode en trois points puis retirer la ponctuation/symboles usuels.
    s = s.replace("…", "...")
    punct = set(string.punctuation) | {"—", "–", "«", "»", "♪", "♫", "·", "•"}
    s = "".join(ch for ch in s if ch not in punct)

    # Retirer les espaces restants
    s = s.strip()

    return len(s) == 0


# -------------------------------------------------------------------
# Synthèse gTTS
# -------------------------------------------------------------------
def _resolve_gtts_lang_tld(voice_id: Optional[str], opts: DubOptions) -> tuple[str, str]:
    """
    Déduit (lang, tld) pour gTTS.
    Priorités :
      1) opts.gtts_lang / opts.gtts_tld si présents
      2) voice_id → 'fr', 'fr-FR', 'en-US', etc. (on prend le préfixe ISO)
      3) défauts (fr, com)
    """
    # 1) depuis les options
    lang = getattr(opts, "gtts_lang", None)
    tld = getattr(opts, "gtts_tld", None)

    # 2) depuis voice_id si non fournis
    if not lang and voice_id:
        s = str(voice_id).strip().lower()
        if "-" in s:
            s = s.split("-")[0]
        lang = s

    # 3) défauts
    lang = (lang or DEFAULT_GTTS_LANG).strip().lower()
    tld = (tld or DEFAULT_GTTS_TLD).strip().lower()

    # Si la lib expose les langues supportées, on vérifie que 'lang' est valide
    if tts_langs is not None:
        try:
            langs = tts_langs()
            if isinstance(langs, dict) and lang not in langs:
                lang = DEFAULT_GTTS_LANG
        except Exception:
            pass

    return lang, tld


def _gtts_synthesize_bytes(text: str, lang: str, tld: str) -> bytes:
    """
    Synthèse gTTS en mémoire → MP3 (bytes).
    """
    _require_gtts()
    buf = io.BytesIO()
    # slow=False = débit normal
    tts = gTTS(text=text, lang=lang, tld=tld, slow=False)
    tts.write_to_fp(buf)
    return buf.getvalue()


def _synthesize(text: str, lang: str, tld: str) -> AudioSegment:
    """
    Enveloppe synchrone pratique (compatible multiprocessing).
    gTTS renvoie du MP3 → on écrit en TMP puis on charge via pydub.
    """
    data = _gtts_synthesize_bytes(text, lang, tld)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3", dir=io_fs.TMP_DIR) as f:
        tmp_path = f.name
        f.write(data)

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
    voice_id: Optional[str],
    opts: DubOptions,
) -> AudioSegment:
    """
    Implémentation gTTS calquée sur tts_edge :
    1) Court-circuit SILENCE si texte vide/ellipses/ponctuation uniquement.
    2) Synthèse protégée (toute erreur → segment muet).
    3) Si opts.min_rate_tts != 1.0 → post-traitement atempo (vitesse minimale globale).
    4) Ajustement à target_duration_ms :
       - si trop long → accélération supplémentaire, bornée par opts.max_rate_tts
       - si trop court → padding silence
    """
    tgt = max(0, int(target_duration_ms))

    # 1) Court-circuit SILENCE
    if _looks_like_silence(text):
        return AudioSegment.silent(duration=tgt)

    # 2) Synthèse protégée
    lang, tld = _resolve_gtts_lang_tld(voice_id, opts)
    try:
        seg = _synthesize(text, lang, tld)
    except Exception:
        # Réseau, quota, texte non supporté, etc. → silence propre
        return AudioSegment.silent(duration=tgt)

    # 3) Vitesse minimale pilotée (post-traitement)
    try:
        base_rate = float(getattr(opts, "min_rate_tts", 1.0) or 1.0)
    except Exception:
        base_rate = 1.0

    if base_rate > 0 and abs(base_rate - 1.0) > 1e-6:
        try:
            seg = _speed_change_with_ffmpeg(seg, base_rate)
        except Exception:
            # On continue avec la synthèse brute si atempo échoue
            pass

    # 4) Ajustement à la durée cible
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
