# add_dub/core/pipeline.py
import os
import subprocess
import time
from dataclasses import dataclass
from typing import Optional

from pydub import AudioSegment

from add_dub.io.fs import join_input, join_output, join_tmp
from add_dub.core.subtitles import parse_srt_file, strip_subtitle_tags_inplace, shift_subtitle_timestamps
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
from add_dub.i18n import t
from add_dub.helpers.console import ask_yes_no

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

    print(t("pipeline_process", name=input_video_name))

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
        print(t("pipeline_no_srt", name=input_video_name))
        return None

    # 4) Nettoyage SRT
    strip_subtitle_tags_inplace(srt_path)

    # 4b) Décalage physique des sous-titres (si demandé)
    if opts.offset_ms != 0:
        print(t("pipeline_offset_shift", ms=opts.offset_ms))
        srt_path = shift_subtitle_timestamps(srt_path, opts.offset_ms)
        # On remet l'offset à 0 pour la suite du pipeline (TTS, ducking, mux)
        # car le fichier SRT est maintenant "physiquement" calé.
        opts.offset_ms = 0

    # --- TRADUCTION (si demandée) ---
    # --- TRADUCTION (si demandée) ---
    if opts.translate and opts.translate_to:
        from add_dub.core.translation import translate_subtitles, write_srt_file
        from add_dub.core.subtitles import parse_srt_file as _parse_srt_simple
        from add_dub.cli.ui import ask_yes_no
        from add_dub.io.fs import join_srt
        
        print(t("pipeline_translating", lang=opts.translate_to))
        
        # Check for existing translated SRT
        base_srt = os.path.basename(srt_path)
        # Save in srt/ folder for persistence and easy access
        new_srt_path = join_srt(f"{base_srt}.{opts.translate_to}.srt")
        
        reuse_existing = False
        if os.path.exists(new_srt_path) and not getattr(opts, "overwrite", False):
            # Ask user if they want to reuse it (unless batch mode)
            print(t("pipeline_trans_found", path=new_srt_path))
            
            should_reuse = False
            if opts.batch_mode:
                should_reuse = True
            elif not opts.ask_reuse_subs:
                # Si configuré pour ne pas demander, on utilise la valeur par défaut
                should_reuse = opts.reuse_translated_subs
            elif ask_yes_no(t("pipeline_trans_reuse"), default=opts.reuse_translated_subs):
                should_reuse = True
                
            if should_reuse:
                reuse_existing = True
                print(t("pipeline_trans_reusing"))
                srt_path = new_srt_path
        
        if not reuse_existing:
            try:
                # On lit le SRT source
                subs_source = _parse_srt_simple(srt_path)
                if subs_source:
                    # Determine source language
                    # Priority: 1. User specified (opts.translate_from)
                    #           2. Filename guess (Sub(Fre))
                    #           3. None (Auto-detect)
                    
                    source_lang = opts.translate_from
                    if source_lang and source_lang.lower() == "auto":
                        source_lang = None
                    
                    if not source_lang:
                        # 1. Guess from filename
                        lower_name = input_video_name.lower()
                        if "sub(fre)" in lower_name or "sub(fr)" in lower_name:
                            source_lang = "fr"
                        elif "sub(eng)" in lower_name or "sub(en)" in lower_name:
                            source_lang = "en"
                        
                        # 2. Detect from content (langdetect)
                        if not source_lang:
                            try:
                                from langdetect import detect
                                # Concatenate a sample of text for better detection
                                sample_text = " ".join([s[2] for s in subs_source[:50]])
                                detected = detect(sample_text)
                                if detected:
                                    source_lang = detected
                                    print(f" [Auto-Detect] Language detected: {source_lang}")
                            except Exception as e:
                                print(f" [Auto-Detect] Failed: {e}")
                    
                    # On traduit
                    subs_translated = translate_subtitles(subs_source, opts.translate_to, source_lang=source_lang)
                    
                    write_srt_file(subs_translated, new_srt_path)
                    
                    # On met à jour srt_path pour que la suite du pipeline utilise le traduit
                    srt_path = new_srt_path
                    print(t("pipeline_trans_done", path=srt_path))
                else:
                    print(t("pipeline_trans_err", err="Empty source SRT"))
            except Exception as e:
                print(t("pipeline_trans_err", err=e))
                # On continue avec le SRT d'origine en cas d'erreur
                pass
    # --------------------------------
    # --------------------------------

    # 5) Libellé langue d'origine
    orig_audio_lang = opts.orig_audio_lang or "Original"

    # 6) Extraction audio d'origine → **tmp/**
    orig_wav = join_tmp(f"{base}_orig.wav")
    print(t("pipeline_extract_audio"))
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
        print(t("pipeline_no_subs_usable"))
        return None

    # 8) Génération TTS alignée → **tmp/**
    tts_wav = join_tmp(f"{test_prefix}{base}_tts.wav")
    print(t("pipeline_gen_tts"))
    svcs.generate_dub_audio(
        srt_file=srt_path,
        output_wav=tts_wav,
        opts=opts,
        duration_limit_sec=limit_duration_sec,
        target_total_duration_ms=orig_len_ms,
    )

    # 9) Ducking → **tmp/**
    ducked_wav = join_tmp(f"{test_prefix}{base}_ducked.wav")
    print(t("pipeline_ducking"))
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

    print(t("pipeline_mux"))
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
        print(t("pipeline_test_header"))
        print(t("pipeline_test_file", path=final_video))
        print(t("pipeline_test_check"))
        while True:
            if not ask_yes_no(t("pipeline_test_ask"), default=False):
                break

            def _ask_float(prompt: str, default_val: float) -> float:
                raw = input(t("ui_prompt_default", prompt=prompt, default=default_val)).strip()
                if not raw:
                    return default_val
                try:
                    return float(raw)
                except Exception:
                    print(t("ui_invalid_value"))
                    return default_val

            # Saisie des nouveaux niveaux
            new_bg = _ask_float(t("pipeline_test_ask_bg"), opts.bg_mix)
            new_tts = _ask_float(t("pipeline_test_ask_tts"), opts.tts_mix)

            # Mise à jour en mémoire
            opts.bg_mix = new_bg
            opts.tts_mix = new_tts

            # Re-mux **sans** régénérer TTS/ducking (on réutilise les WAV temporaires)
            print(t("pipeline_test_remux"))
            dub_in_one_pass(
                video_fullpath=input_video_path,
                bg_wav=ducked_wav,
                tts_wav=tts_wav,
                original_wav=orig_wav,
                subtitle_srt_path=srt_path,
                output_video_path=final_video,  # on écrase, -y est passé dans la commande
                opts=opts,
            )
            print(t("pipeline_test_done", path=final_video))
            print(t("pipeline_test_continue"))

    # 12) Nettoyage des **tmp/**
    for f in (orig_wav, tts_wav, ducked_wav):
        try:
            if f and os.path.exists(f):
                os.remove(f)
        except Exception:
            pass

    return final_video
