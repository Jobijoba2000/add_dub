# add_dub/__main__.py

import os
import sys
from dataclasses import replace

from add_dub.io.fs import ensure_base_dirs, join_input
from add_dub.core.subtitles import list_input_videos
from add_dub.core.pipeline import DubOptions, Services, process_one_video
from add_dub.core.tts_generate import generate_dub_audio
from add_dub.cli.ui import ask_option, ask_mode, ask_yes_no, ask_float, ask_int, ask_str
from add_dub.cli.selectors import (
    choose_files,
    choose_audio_track_ffmpeg_index,
    choose_subtitle_source,
)
from add_dub.core.codecs import final_audio_codec_args, subtitle_codec_for_container
from add_dub.config import cfg
from add_dub.helpers.time import measure_duration as _md
from add_dub.config.opts_loader import load_options

opts = load_options()

def _resolve_srt_for_video_impl(video_fullpath: str, sub_choice: tuple) -> str | None:
    from add_dub.core.subtitles import resolve_srt_for_video
    return resolve_srt_for_video(video_fullpath, sub_choice)

def _generate_dub_audio_impl(
    *,
    srt_file: str,
    output_wav: str,
    voice_id: str | None,
    duration_limit_sec: int | None,
    target_total_duration_ms: int | None,
    offset_ms: int,
) -> str:
    return generate_dub_audio(
        srt_file,
        output_wav,
        voice_id or "",
        duration_limit_sec=duration_limit_sec,
        target_total_duration_ms=target_total_duration_ms,
        offset_ms=offset_ms,
    )

def build_services() -> Services:
    return Services(
        resolve_srt_for_video=_resolve_srt_for_video_impl,
        generate_dub_audio=_generate_dub_audio_impl,
        choose_audio_track=choose_audio_track_ffmpeg_index,
        choose_subtitle_source=choose_subtitle_source,
    )

def build_default_opts() -> DubOptions:
    # Pas de changement côté codecs/containers (gérés ailleurs)
    audio_codec=str(opts["audio_codec"].value) if "audio_codec" in opts else cfg.AUDIO_CODEC
    audio_bitrate=int(opts["audio_bitrate"].value) if "audio_bitrate" in opts else cfg.AUDIO_BITRATE
    audio_args = final_audio_codec_args(audio_codec, f"{audio_bitrate}k")
    sub_codec = subtitle_codec_for_container(cfg.AUDIO_CODEC_FINAL)
    return DubOptions(
        audio_ffmpeg_index=None,
        sub_choice=None,
        orig_audio_lang=opts["orig_audio_lang"].value if "orig_audio_lang" in opts else cfg.ORIG_AUDIO_LANG,
        db_reduct=float(opts["db"].value) if "db" in opts else cfg.DB_REDUCT,
        offset_ms=int(opts["offset"].value) if "offset" in opts else cfg.OFFSET_STR,
        bg_mix=float(opts["bg"].value) if "bg" in opts else cfg.BG_MIX,
        tts_mix=float(opts["tts"].value) if "tts" in opts else cfg.TTS_MIX,
        audio_codec=audio_codec,
        audio_bitrate=audio_bitrate,
        voice_id=None,  # voix par défaut système
        audio_codec_args=tuple(audio_args),
        sub_codec=sub_codec,
    )


def _ask_config_for_video(
    *,
    base_opts: DubOptions,
    svcs: Services,
    video_fullpath: str,
    force_choose_tracks_and_subs: bool = True,
) -> DubOptions | None:
    """
    Pose toutes les questions pour une vidéo :
      - piste audio (jamais de valeur par défaut)
      - source sous-titres (jamais de valeur par défaut)
      - libellé, ducking dB, offset, BG, TTS (défauts = base_opts)
    Retourne les options complètes, ou None si annulation faute de ST.
    """
    aidx = base_opts.audio_ffmpeg_index
    sc = base_opts.sub_choice

    if force_choose_tracks_and_subs:
        aidx = svcs.choose_audio_track(video_fullpath)
        sc = svcs.choose_subtitle_source(video_fullpath)
        if sc is None:
            print("Aucune source de sous-titres choisie.")
            return None
      
    # label = svcs.ask_str("Libellé piste d'origine", base_opts.orig_audio_name or "Original")
    oal = ask_option("orig_audio_lang", opts, "str", "Langue originale", base_opts.orig_audio_lang)
    db  = ask_option("db", opts, "float", "Réduction (ducking) en dB", base_opts.db_reduct)
    off = ask_option("offset", opts, "int",   "Décalage ST/TTS (ms, négatif = plus tôt)", base_opts.offset_ms)
    bg  = ask_option("bg", opts, "float",     "Niveau BG (1.0 = inchangé)",               base_opts.bg_mix)
    tts = ask_option("tts", opts, "float",    "Niveau TTS (1.0 = inchangé)",base_opts.tts_mix)
    ac = ask_option("audio_codec", opts, "str", "Codec audio", base_opts.audio_codec)
    ab = ask_option("audio_bitrate", opts, "int", "Bitrate", base_opts.audio_bitrate)

    return replace(
        base_opts,
        audio_ffmpeg_index=aidx,
        sub_choice=sc,
        orig_audio_lang=oal,
        db_reduct=db,
        offset_ms=off,
        bg_mix=bg,
        tts_mix=tts,
        audio_codec=ac,
        audio_bitrate=ab,
        audio_codec_args=final_audio_codec_args(ac, f"{ab}k"),
    )


def _cleanup_test_outputs(output_path: str | None) -> None:
    """Supprime le fichier de sortie de test si présent."""
    if not output_path:
        return
    try:
        if os.path.isfile(output_path):
            os.remove(output_path)
            print(f"[TEST] Fichier supprimé : {output_path}")
    except Exception as e:
        print(f"[TEST] Impossible de supprimer le fichier de test ({output_path}) : {e}")


def main() -> int:
    while True:
        ensure_base_dirs()

        files = list_input_videos()
        selected = choose_files(files)
        if not selected:
            print("Aucun fichier sélectionné.")
            return 1

        mode = ask_mode().strip().lower()
        svcs = build_services()

        if mode.startswith("a"):  # AUTO
            print("\n[Auto] Configuration/test sur la première vidéo, application au lot si validé.")
            first = selected[0]
            first_full = join_input(first)

            # Base pour paramétrer (servira uniquement d'init pour les champs non audio/ST pendant les re-tests)
            base_for_tests = build_default_opts()

            # Si on choisit de tester, boucle test → question → éventuel re-test
            validated_opts = None
            if ask_yes_no("Faire un test de 5 minutes ?", True):
                while True:
                    cfg = _ask_config_for_video(
                        base_opts=base_for_tests,
                        svcs=svcs,
                        video_fullpath=first_full,
                        force_choose_tracks_and_subs=True,  # toujours re-choisir audio/ST sans défaut
                    )
                    if cfg is None:
                        return 1

                    out_test = None
                    try:
                        out_test = _md(
                            process_one_video, 
                            first,
                            cfg,
                            svcs,
                            limit_duration_sec=300,
                            test_prefix="TEST_",
                        )
                        if out_test:
                            print(f"[TEST] OK → {out_test}")
                    except Exception as e:
                        print(f"[TEST] Erreur: {e}")

                    test_ok = ask_yes_no("Le test est-il OK et valide les réglages ?", True)
                    _cleanup_test_outputs(out_test)

                    if test_ok:
                        validated_opts = cfg
                        break
                    else:
                        # Pour le re-test sur la même vidéo :
                        #   - audio/ST seront re-demandés sans défaut
                        #   - les autres champs utiliseront comme défauts ceux de ce test raté
                        print(cfg)
                        base_for_tests = replace(
                            cfg,
                            audio_ffmpeg_index=None,
                            sub_choice=None,
                        )
                        # et on relance la boucle
            else:
                # Pas de test : configurer une fois
                cfg = _ask_config_for_video(
                    base_opts=base_for_tests,
                    svcs=svcs,
                    video_fullpath=first_full,
                    force_choose_tracks_and_subs=True,
                )
                if cfg is None:
                    return 1
                validated_opts = cfg

            # Traitement de toutes les vidéos avec les réglages validés
            for v in selected:
                try:
                    outp = _md(process_one_video, v, validated_opts, svcs)
                    if outp:
                        print(f"[OK] {v} → {outp}")
                except Exception as e:
                    print(f"[ERREUR] {v} → {e}")

            print("\nTerminé.")

        else:  # MANUEL
            print("\n[Manuel] Chaque vidéo repart de zéro. Les défauts ne sont conservés que pendant les re-tests de la même vidéo (hors audio/ST).")

            for v in selected:
                print(f"\n[Manuel] Vidéo : {v}")
                v_full = join_input(v)

                # Base de départ pour cette vidéo : defaults globaux (aucune persistance inter-vidéos)
                base_for_this_video = build_default_opts()

                # Configuration initiale (audio/ST re-choisis, sans défaut)
                cur = _ask_config_for_video(
                    base_opts=base_for_this_video,
                    svcs=svcs,
                    video_fullpath=v_full,
                    force_choose_tracks_and_subs=True,
                )
                if cur is None:
                    print("Aucune source de sous-titres choisie. Vidéo ignorée.")
                    continue

                # Boucle de test optionnelle pour cette vidéo
                if ask_yes_no("Faire un test de 5 minutes pour cette vidéo ?", True):
                    while True:
                        out_test = None
                        try:
                            out_test = _md(
                                process_one_video, 
                                v,
                                cur,
                                svcs,
                                limit_duration_sec=300,
                                test_prefix="TEST_",
                            )
                            if out_test:
                                print(f"[TEST] OK → {out_test}")
                        except Exception as e:
                            print(f"[TEST] Erreur: {e}")

                        test_ok = ask_yes_no("Le test est-il OK et valide les réglages pour cette vidéo ?", True)
                        _cleanup_test_outputs(out_test)

                        if test_ok:
                            break
                        else:
                            # Re-test : on remet en questions audio/ST (sans défaut),
                            # et les autres champs prennent pour défauts ceux du test précédent.
                            base_for_this_video = replace(
                                cur,
                                audio_ffmpeg_index=None,
                                sub_choice=None,
                            )
                            maybe = _ask_config_for_video(
                                base_opts=base_for_this_video,
                                svcs=svcs,
                                video_fullpath=v_full,
                                force_choose_tracks_and_subs=True,
                            )
                            if maybe is None:
                                print("Aucune source de sous-titres choisie. Abandon de cette vidéo.")
                                cur = None
                                break
                            cur = maybe
                            # et on relance un test

                if cur is None:
                    print("Configuration annulée pour cette vidéo.")
                    continue

                # Traitement complet pour cette vidéo
                try:
                    outp = _md(process_one_video, v, cur, svcs)
                    if outp:
                        print(f"[OK] {v} → {outp}")
                except Exception as e:
                    print(f"[ERREUR] {v} → {e}")

            print("\nTerminé.")

        # Fin de cycle : proposer de relancer un lot
        choix = input("Voulez-vous générer une autre vidéo ? (o/n) : ").strip().lower()
        if not choix.startswith("o"):
            return 0


if __name__ == "__main__":
    from multiprocessing import freeze_support
    freeze_support()
    sys.exit(main())
