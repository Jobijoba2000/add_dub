import os
import json
from dataclasses import replace
from pathlib import Path
from typing import Optional

from add_dub.io.fs import join_output, join_tmp
from add_dub.core.subtitles import parse_srt_file, strip_subtitle_tags_inplace, shift_subtitle_timestamps
from add_dub.core.ducking import lower_audio_during_subtitles
from add_dub.adapters.ffmpeg import (
    extract_audio_track,
    dub_in_one_pass,
)
from add_dub.core.options import DubOptions
from add_dub.core.services import Services
from add_dub.logger import (log_call, log_time)
from add_dub.i18n import t
from add_dub.progress import emit, stage

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


@log_time
@log_call
def _process_one_video(
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
    opts = replace(opts)

    base, ext = os.path.splitext(os.path.basename(input_video_path))

    svcs.ui.message(t("pipeline_process", name=input_video_name))

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

    from add_dub.core.languages import source_languages, language_code, voice_language, voice_locale, external_subtitle_language
    original_language, subtitle_language = source_languages(input_video_path, audio_idx, sub_choice)
    try:
        voices = list_available_voices()
    except Exception:
        voices = []
    dubbed_language = voice_language(opts.voice_id, voices)
    opts = replace(opts, original_language=original_language,
                   dubbed_language=dubbed_language, dubbed_locale=voice_locale(opts.voice_id, voices),
                   subtitle_language=subtitle_language)

    # 3) Résolution vers un SRT exploitable
    emit('plan', subtitles=sub_choice[0] != 'srt', translation=bool(opts.translate and opts.translate_to))
    if sub_choice[0] != 'srt':
        stage('subtitles')
    srt_path = svcs.resolve_srt_for_video(input_video_path, sub_choice, ui=svcs.ui)
    if not srt_path:
        svcs.ui.error(t("pipeline_no_srt", name=input_video_name))
        return None

    if opts.subtitle_language == 'und':
        opts = replace(opts, subtitle_language=external_subtitle_language(srt_path, opts.translate_from))

    # 4) Nettoyage SRT
    if os.getenv('ADD_DUB_PREVIEW_RANGE'):
        import shutil
        local_srt = join_tmp('preview-input.srt')
        shutil.copyfile(srt_path, local_srt)
        srt_path = local_srt
    strip_subtitle_tags_inplace(srt_path)

    # 4b) Décalage physique des sous-titres (si demandé)
    if opts.offset_ms != 0:
        svcs.ui.message(t("pipeline_offset_shift", ms=opts.offset_ms))
        srt_path = shift_subtitle_timestamps(srt_path, opts.offset_ms)
        # On remet l'offset à 0 pour la suite du pipeline (TTS, ducking, mux)
        # car le fichier SRT est maintenant "physiquement" calé.
        opts = replace(opts, offset_ms=0)

    if os.getenv('ADD_DUB_PREVIEW_RANGE'):
        from add_dub.core.preview import prepare_excerpt
        import add_dub.io.fs as preview_fs
        start, end = json.loads(os.environ['ADD_DUB_PREVIEW_RANGE'])
        # Les traductions de l’essai restent elles aussi dans le répertoire isolé.
        preview_fs.SRT_DIR = preview_fs.get_tmp_dir()
        input_video_path, srt_path, audio_idx = prepare_excerpt(
            input_video_path, srt_path, audio_idx, start, end, preview_fs.get_tmp_dir(),
            progress_cb=lambda value: emit('preview_extract', value=value))
        limit_duration_sec = None

    if limit_duration_sec is not None:
        # FFmpeg's output -t does not shorten the duration of a subtitle packet
        # that starts before the cut. Use clipped cues for translation and mux
        # as well as TTS, without changing the persistent full-episode SRT.
        from add_dub.core.translation import write_srt_file
        limited_srt = join_tmp(Path(srt_path).stem + f'.limit-{limit_duration_sec}.srt')
        write_srt_file(parse_srt_file(srt_path, duration_limit_sec=limit_duration_sec), limited_srt)
        srt_path = limited_srt

    # --- TRADUCTION (si demandée) ---
    if opts.translate and opts.translate_to:
        stage('translation')
        from add_dub.core.translation import translate_subtitles, write_srt_file
        from add_dub.core.subtitles import parse_srt_file as _parse_srt_simple
        from add_dub.io.fs import join_srt

        svcs.ui.message(t("pipeline_translating", lang=opts.translate_to))

        # Check for existing translated SRT
        import re as _re
        base_srt = os.path.basename(srt_path)
        clean_base_srt = _re.sub(r'\.[a-z]{2,3}\.srt$', '.srt', base_srt, flags=_re.IGNORECASE)
        new_srt_path = join_srt(f"{clean_base_srt}.{opts.translate_to}.srt")

        reuse_existing = False
        should_reuse = bool(getattr(opts, "reuse_translated_subs", True)) and not getattr(opts, "overwrite", False)

        if should_reuse and os.path.exists(new_srt_path):
            if not opts.batch_mode and getattr(opts, "ask_reuse_subs", False):
                if svcs.ui.ask_yes_no(t("pipeline_trans_reuse"), default=True):
                    reuse_existing = True
            else:
                reuse_existing = True

            if reuse_existing:
                emit('skip', name='translation')
                svcs.ui.message(t("pipeline_trans_found", path=new_srt_path))
                svcs.ui.message(t("pipeline_trans_reusing"))
                srt_path = new_srt_path
                opts = replace(opts, subtitle_language=language_code(opts.translate_to))
        else:
            # Si on ne réutilise pas : on supprime l'ancien fichier traduit existant pour forcer une nouvelle traduction
            if os.path.exists(new_srt_path):
                try:
                    os.remove(new_srt_path)
                except Exception:
                    pass

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
                                sample_text = " ".join([s[2] for s in subs_source[:50]])
                                detected = detect(sample_text)
                                if detected:
                                    source_lang = detected
                                    svcs.ui.message(f" [Auto-Detect] Language detected: {source_lang}")
                            except Exception as e:
                                svcs.ui.error(f" [Auto-Detect] Failed: {e}")

                    src = (source_lang or "fr").strip().lower()[:2]
                    tgt = (opts.translate_to or "fr").strip().lower()[:2]

                    # Vérification source == cible
                    skip_trans = False
                    if src == tgt:
                        if opts.batch_mode:
                            svcs.ui.message(t("pipeline_trans_same_lang_skip", src=src, tgt=tgt))
                            skip_trans = True
                        else:
                            svcs.ui.message(t("pipeline_trans_same_lang_warn", src=src, tgt=tgt))
                            if svcs.ui.ask_yes_no(t("pipeline_trans_same_lang_ask"), default=False):
                                from add_dub.helpers.console import ask_string
                                while True:
                                    new_tgt = ask_string(t("cli_ask_translate_lang", default=tgt), default=tgt).strip().lower()
                                    if len(new_tgt) == 2 and new_tgt.isalpha():
                                        tgt = new_tgt
                                        break
                                    svcs.ui.message(t("cli_lang_code_invalid"))

                                while True:
                                    new_src = ask_string(t("cli_ask_translate_from", default=src), default=src).strip().lower()
                                    if new_src in ("auto", "none", ""):
                                        source_lang = None
                                        break
                                    if len(new_src) == 2 and new_src.isalpha():
                                        src = new_src
                                        source_lang = new_src
                                        break
                                    svcs.ui.message(t("cli_lang_source_invalid"))

                                opts = replace(opts, translate_to=tgt, translate_from=source_lang)
                                if src == tgt:
                                    svcs.ui.message(t("pipeline_trans_same_lang_skip", src=src, tgt=tgt))
                                    skip_trans = True
                            else:
                                svcs.ui.message(t("pipeline_trans_same_lang_skip", src=src, tgt=tgt))
                                skip_trans = True

                    if not skip_trans:
                        while True:
                            new_srt_path = join_srt(f"{base_srt}.{tgt}.srt")
                            subs_translated = translate_subtitles(subs_source, tgt, source_lang=source_lang, ui=svcs.ui, engine=getattr(opts, "translation_engine", "google"))
                            if subs_translated is not None:

                                write_srt_file(subs_translated, new_srt_path)
                                srt_path = new_srt_path
                                opts = replace(opts, subtitle_language=language_code(tgt))
                                svcs.ui.message(t("pipeline_trans_done", path=srt_path))
                                break
                            else:
                                svcs.ui.error(t("pipeline_trans_model_not_found", src=src, tgt=tgt))
                                if not opts.batch_mode and svcs.ui.ask_yes_no(t("pipeline_trans_retry_ask"), default=False):
                                    from add_dub.helpers.console import ask_string
                                    while True:
                                        new_tgt = ask_string(t("cli_ask_translate_lang", default=tgt), default=tgt).strip().lower()
                                        if len(new_tgt) == 2 and new_tgt.isalpha():
                                            tgt = new_tgt
                                            break
                                        svcs.ui.message(t("cli_lang_code_invalid"))
                                    opts = replace(opts, translate_to=tgt)
                                    continue
                                else:
                                    svcs.ui.message(t("pipeline_trans_fallback_orig"))
                                    break
                else:
                    svcs.ui.error(t("pipeline_trans_err", err="Empty source SRT"))
                if subs_source and skip_trans:
                    emit('skip', name='translation')
            except Exception as e:
                svcs.ui.error(t("pipeline_trans_err", err=e))
                # On continue avec le SRT d'origine en cas d'erreur
                pass
    # --------------------------------
    # --------------------------------

    # 5) Libellé langue d'origine
    opts = replace(opts, audio_ffmpeg_index=audio_idx)

    # 6) Extraction audio d'origine → **tmp/**
    orig_wav = join_tmp(f"{base}_orig.wav")
    stage('audio')
    svcs.ui.message(t("pipeline_extract_audio"))
    extract_audio_track(
        input_video_path,
        audio_idx,
        orig_wav,
        duration_sec=limit_duration_sec,
        progress_cb=svcs.ui.progress,
    )

    # Durée cible (utile pour calages éventuels)
    try:
        from add_dub.adapters.ffmpeg import media_duration
        orig_len_ms = round(media_duration(orig_wav) * 1000)
    except Exception:
        orig_len_ms = None

    # 7) Parsing SRT (sert aussi au ducking)
    subtitles = parse_srt_file(srt_path, duration_limit_sec=limit_duration_sec)
    if not subtitles:
        svcs.ui.error(t("pipeline_no_subs_usable"))
        return None

    # 8) Génération TTS alignée → **tmp/**
    tts_wav = join_tmp(f"{test_prefix}{base}_tts.wav")
    stage('tts')
    svcs.ui.message(t("pipeline_gen_tts"))
    svcs.generate_dub_audio(
        srt_file=srt_path,
        output_wav=tts_wav,
        opts=opts,
        duration_limit_sec=limit_duration_sec,
        target_total_duration_ms=orig_len_ms,
        ui=svcs.ui,
    )

    # 9) Ducking → **tmp/**
    ducked_wav = join_tmp(f"{test_prefix}{base}_ducked.wav")
    stage('ducking')
    svcs.ui.message(t("pipeline_ducking"))
    lower_audio_during_subtitles(
        audio_file=orig_wav,
        subtitles=subtitles,
        output_wav=ducked_wav,
        reduction_db=opts.db_reduct,
        offset_ms=opts.offset_ms,
        progress_cb=svcs.ui.progress,
    )

    # 10) Sortie finale
    final_ext = ".mkv"  # conteneur cible

    dub_code = _dub_code_from_voice(getattr(opts, 'voice_id', None))
    final_video = join_output(f"{test_prefix}{base} [dub-{dub_code}]{final_ext}", output_dir_path)

    svcs.ui.message(t("pipeline_mux"))
    stage('mux')
    # La GUI ne publie le MKV qu’après la sortie réussie du processus.
    # Un arrêt pendant le mixage ne touche ainsi aucune sortie précédente.
    mux_output = os.environ.get('ADD_DUB_GUI_PARTIAL_OUTPUT') or final_video
    # En interactif, remplacer la vidéo comme auparavant, sans forcer
    # la régénération des traductions réutilisables.
    mux_opts = replace(opts, overwrite=opts.overwrite or not opts.batch_mode)
    dub_in_one_pass(
        video_fullpath=input_video_path,
        bg_wav=ducked_wav,
        tts_wav=tts_wav,
        original_wav=orig_wav,
        subtitle_srt_path=srt_path,
        output_video_path=mux_output,
        opts=mux_opts,
        progress_cb=svcs.ui.progress,
        duration_sec=limit_duration_sec,
    )

    # 11) (NOUVEAU) Option de test AVANT nettoyage + re-mux rapide si besoin
    if getattr(opts, "ask_test_before_cleanup", False):
        svcs.ui.message(t("pipeline_test_header"))
        svcs.ui.message(t("pipeline_test_file", path=final_video))
        svcs.ui.message(t("pipeline_test_check"))
        while True:
            if not svcs.ui.ask_yes_no(t("pipeline_test_ask"), default=False):
                break

            # Saisie des nouveaux niveaux
            new_bg = svcs.ui.ask_float(t("pipeline_test_ask_bg"), opts.bg_mix)
            new_tts = svcs.ui.ask_float(t("pipeline_test_ask_tts"), opts.tts_mix)

            # Mise à jour en mémoire
            opts = replace(opts, bg_mix=new_bg, tts_mix=new_tts, overwrite=True)

            # Re-mux **sans** régénérer TTS/ducking (on réutilise les WAV temporaires)
            svcs.ui.message(t("pipeline_test_remux"))
            dub_in_one_pass(
                video_fullpath=input_video_path,
                bg_wav=ducked_wav,
                tts_wav=tts_wav,
                original_wav=orig_wav,
                subtitle_srt_path=srt_path,
                output_video_path=mux_output,  # on écrase, -y est passé dans la commande
                opts=opts,
                progress_cb=svcs.ui.progress,
            )
            svcs.ui.message(t("pipeline_test_done", path=final_video))
            svcs.ui.message(t("pipeline_test_continue"))

    # 12) Nettoyage des **tmp/**
    for f in (orig_wav, tts_wav, ducked_wav):
        try:
            if f and os.path.exists(f):
                os.remove(f)
        except Exception:
            pass

    if os.environ.get('ADD_DUB_GUI_PARTIAL_OUTPUT'):
        with open(os.path.join(os.environ['ADD_DUB_GUI_WORK_TMP'], 'result.json'), 'w', encoding='utf-8') as manifest:
            json.dump({'destination': final_video, 'overwrite': mux_opts.overwrite}, manifest)
    return final_video


def process_one_video(**kwargs):
    """Un dossier de travail par vidéo, nettoyé aussi en cas d'échec."""
    from add_dub.io.work import work_directory, OFFLINE, is_offline
    from add_dub.io import fs
    from add_dub.core import translation
    from add_dub.core.validation import validate_options
    validate_options(kwargs['opts'])
    # Les sorties ignorées ne font pas partie du traitement chronométré.
    opts = kwargs['opts']
    svcs = kwargs['svcs']
    input_video_path = kwargs['input_video_path']
    output_dir_path = kwargs.get('output_dir_path')
    test_prefix = kwargs.get('test_prefix', '')
    base = os.path.splitext(os.path.basename(input_video_path))[0]
    from add_dub.adapters.ffmpeg import validate_media
    dub_code = _dub_code_from_voice(opts.voice_id)
    final_video = join_output(f"{test_prefix}{base} [dub-{dub_code}].mkv", output_dir_path)
    if os.path.exists(final_video) and not opts.overwrite:
        if opts.skip_existing:
            validate_media(final_video)
            emit('existing_output', path=final_video)
            svcs.ui.message(f"[SKIP] Fichier déjà existant : {os.path.basename(final_video)}")
            return final_video
        if opts.batch_mode:
            raise FileExistsError(f'Sortie existante : {final_video}. Utilisez --overwrite ou --skip-existing.')

    kwargs['opts'] = opts
    with work_directory() as directory:
        kwargs['opts'] = replace(kwargs['opts'], work_dir=directory, offline=kwargs['opts'].offline or is_offline())
        token = OFFLINE.set(kwargs['opts'].offline)
        translation_token = translation.OFFLINE.set(kwargs['opts'].offline)
        original_srt_dir = fs.SRT_DIR
        try:
            return _process_one_video(**kwargs)
        finally:
            fs.SRT_DIR = original_srt_dir
            translation.OFFLINE.reset(translation_token)
            OFFLINE.reset(token)
