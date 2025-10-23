# add_dub/core/pipeline.py
import os
import subprocess
import time
from dataclasses import dataclass
from typing import Optional

from pydub import AudioSegment

from add_dub.io.fs import join_input, join_output, join_tmp
from add_dub.core.subtitles import parse_srt_file, strip_subtitle_tags_inplace
from add_dub.core.ducking import lower_audio_during_subtitles
from add_dub.adapters.ffmpeg import (
    extract_audio_track,
    dub_in_one_pass,
)
import re
from add_dub.core.options import DubOptions
from add_dub.core.services import Services
from pprint import pprint
from add_dub.logger import (log_call, log_time)


@log_time
@log_call
def process_one_video(
    *,
    input_video_path: str,
    input_video_name: str,
    output_dir_path: Optional[str] = None,
    opts: DubOptions,
    svcs: Services,
    limit_duration_sec: Optional[int] = None,
    test_prefix: str = "",
) -> Optional[str]:
    """
    Traite UNE vidéo avec les options et services fournis.
    Retourne le chemin de la vidéo finale, ou None si annulé.
    """

    print(input_video_name)

    base, ext = os.path.splitext(os.path.basename(input_video_path))

    # 1) Piste audio source
    audio_idx = opts.audio_ffmpeg_index
    if audio_idx is None:
        audio_idx = svcs.choose_audio_track(input_video_path)

    # 2) Source des sous-titres
    sub_choice = opts.sub_choice
    if sub_choice is None:
        sub_choice = svcs.choose_subtitle_source(input_video_path)
        if sub_choice is None:
            return None

    # 3) Résolution vers un SRT exploitable
    srt_path = svcs.resolve_srt_for_video(input_video_path, sub_choice)
    if not srt_path:
        print(f"Impossible d'obtenir un SRT pour {input_video_name}.")
        return None

    # 4) Nettoyage SRT
    strip_subtitle_tags_inplace(srt_path)

    # 5) Libellé langue d'origine
    orig_audio_lang = opts.orig_audio_lang or "Original"

    # 6) Extraction audio d'origine → **tmp/**
    orig_wav = join_tmp(f"{base}_orig.wav")
    print("\nExtraction de l'audio d'origine (WAV PCM)...")
    extract_audio_track(
        input_video_path,
        audio_idx,
        orig_wav,
        duration_sec=limit_duration_sec
    )

    # Durée cible (utile pour calages éventuels)
    try:
        orig_len_ms = len(AudioSegment.from_file(orig_wav))
    except Exception:
        orig_len_ms = None

    # 7) Parsing SRT (sert aussi au ducking)
    subtitles = parse_srt_file(srt_path, duration_limit_sec=limit_duration_sec)
    if not subtitles:
        print("Aucun sous-titre exploitable.")
        return None

    # 8) Génération TTS alignée → **tmp/**
    tts_wav = join_tmp(f"{test_prefix}{base}_tts.wav")
    print("\nGénération TTS (WAV)...")
    svcs.generate_dub_audio(
        srt_file=srt_path,
        output_wav=tts_wav,
        opts=opts,
        duration_limit_sec=limit_duration_sec,
        target_total_duration_ms=orig_len_ms,
    )

    # 9) Ducking → **tmp/**
    ducked_wav = join_tmp(f"{test_prefix}{base}_ducked.wav")
    print("\nDucking de l'audio original pendant les dialogues...")
    lower_audio_during_subtitles(
        audio_file=orig_wav,
        subtitles=subtitles,
        output_wav=ducked_wav,
        reduction_db=opts.db_reduct,
        offset_ms=opts.offset_ms,
    )

    # 10) Sortie finale
    final_ext = ".mkv"  # conteneur cible

    # code dub pour suffix
    from add_dub.core.tts import list_available_voices
    def _dub_code_from_voice(voice_id: str | None) -> str:
        if not voice_id:
            return "fr"
        try:
            voices = list_available_voices()
        except Exception:
            voices = []
        lang = ""
        vid = str(voice_id).strip()
        for v in voices:
            if str(v.get("id", "")).strip() == vid:
                lang = (v.get("lang") or "").strip()
                break
        if not lang:
            import re as _re
            m = _re.search(r"([a-zA-Z]{2})(?:[-_][A-Za-z]{2})?", vid)
            if m:
                lang = m.group(0)
        base_lang = (lang.split("-")[0] if lang else "fr").lower()
        import re as _re
        return _re.sub(r"[^a-z]", "", base_lang) or "fr"

    dub_code = _dub_code_from_voice(getattr(opts, 'voice_id', None))
    final_video = join_output(f"{test_prefix}{base} [dub-{dub_code}]{final_ext}", output_dir_path)

    print("\nMixage/Encodage/Mux final...")
    dub_in_one_pass(
        video_fullpath=input_video_path,
        bg_wav=ducked_wav,
        tts_wav=tts_wav,
        original_wav=orig_wav,
        subtitle_srt_path=srt_path,
        output_video_path=final_video,
        opts=opts,
    )

    # 11) (NOUVEAU) Option de test AVANT nettoyage + re-mux rapide si besoin
    if getattr(opts, "ask_test_before_cleanup", False):
        print("\n=== TEST AVANT NETTOYAGE ===")
        print(f"Fichier généré : {final_video}")
        print("Ouvrez la vidéo et vérifiez les niveaux (bg / tts).")
        while True:
            resp = input("Souhaitez-vous ajuster les niveaux et refaire le mux ? (o/n) : ").strip().lower()
            if resp not in ("o", "oui", "y", "yes", "n", "non"):
                continue
            if resp in ("n", "non"):
                break

            def _ask_float(prompt: str, default_val: float) -> float:
                raw = input(f"{prompt} (Entrée pour garder {default_val}) : ").strip()
                if not raw:
                    return default_val
                try:
                    return float(raw)
                except Exception:
                    print("Valeur invalide, on conserve la valeur actuelle.")
                    return default_val

            # Saisie des nouveaux niveaux
            new_bg = _ask_float("Nouveau niveau BG (volume background, ex. 1.0, 2.5)", opts.bg_mix)
            new_tts = _ask_float("Nouveau niveau TTS (volume voix, ex. 1.0, 3.0)", opts.tts_mix)

            # Mise à jour en mémoire
            opts.bg_mix = new_bg
            opts.tts_mix = new_tts

            # Re-mux **sans** régénérer TTS/ducking (on réutilise les WAV temporaires)
            print("\nRe-mux avec nouveaux niveaux...")
            dub_in_one_pass(
                video_fullpath=input_video_path,
                bg_wav=ducked_wav,
                tts_wav=tts_wav,
                original_wav=orig_wav,
                subtitle_srt_path=srt_path,
                output_video_path=final_video,  # on écrase, -y est passé dans la commande
                opts=opts,
            )
            print(f"Re-mux terminé → {final_video}")
            print("Réouvrez la vidéo pour vérifier. CTRL+C pour quitter, sinon poursuivez.")

    # 12) Nettoyage des **tmp/**
    for f in (orig_wav, tts_wav, ducked_wav):
        try:
            if f and os.path.exists(f):
                os.remove(f)
        except Exception:
            pass

    return final_video
