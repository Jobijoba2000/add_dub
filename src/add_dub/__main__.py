# src/add_dub/__main__.py

import sys
from dataclasses import replace

from add_dub.io.fs import ensure_base_dirs
from add_dub.core.subtitles import list_input_videos
from add_dub.core.pipeline import DubOptions, Services, process_one_video
from add_dub.core.tts_generate import generate_dub_audio
from add_dub.cli.ui import ask_mode, ask_yes_no, ask_float, ask_int, ask_str
from add_dub.cli.selectors import (
    choose_files,
    choose_audio_track_ffmpeg_index,
    choose_subtitle_source,
)
from add_dub.core.codecs import final_audio_codec_args, subtitle_codec_for_container
from add_dub.config import cfg
from add_dub.io.fs import join_input

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
        ask_str=ask_str,
    )


def build_default_opts() -> DubOptions:
    audio_args = final_audio_codec_args(cfg.AUDIO_CODEC_FINAL, cfg.AUDIO_BITRATE)
    sub_codec = subtitle_codec_for_container(cfg.AUDIO_CODEC_FINAL)
    return DubOptions(
        audio_ffmpeg_index=None,
        sub_choice=None,
        orig_audio_name="Original",
        db_reduct=cfg.DB_REDUCT,
        offset_ms=cfg.OFFSET_STR,
        bg_mix=cfg.BG_MIX,
        tts_mix=cfg.TTS_MIX,
        voice_id=None,  # voix par défaut système
        audio_codec_args=tuple(audio_args),
        sub_codec=sub_codec,
    )


def main() -> int:
    ensure_base_dirs()

    files = list_input_videos()
    selected = choose_files(files)
    if not selected:
        print("Aucun fichier sélectionné.")
        return 1

    mode = ask_mode()
    svcs = build_services()

    if mode.lower().startswith("a"):  # AUTO
        opts = build_default_opts()
        first = selected[0]
        first_full = join_input(first)

        print(f"\n[Auto] Configuration initiale sur : {first}")

        # Choix piste + ST une fois
        aidx = svcs.choose_audio_track(first_full)
        sc = svcs.choose_subtitle_source(first_full)
        if sc is None:
            print("Aucune source de sous-titres choisie.")
            return 1

        label = svcs.ask_str("Libellé piste d'origine", opts.orig_audio_name or "Original")
        db = ask_float("Réduction (ducking) en dB", opts.db_reduct)
        off = ask_int("Décalage ST/TTS (ms, négatif = plus tôt)", opts.offset_ms)
        bg = ask_float("Niveau BG (1.0 = inchangé)", opts.bg_mix)
        tts = ask_float("Niveau TTS (1.0 = inchangé)", opts.tts_mix)

        opts = replace(
            opts,
            audio_ffmpeg_index=aidx,
            sub_choice=sc,
            orig_audio_name=(label or "Original"),
            db_reduct=db,
            offset_ms=off,
            bg_mix=bg,
            tts_mix=tts,
        )

        do_test = ask_yes_no("Faire un test de 5 minutes ?", True)
        if do_test:
            try:
                out_test = process_one_video(first, opts, svcs, limit_duration_sec=300, test_prefix="TEST_")
                if out_test:
                    print(f"[TEST] OK → {out_test}")
            except Exception as e:
                print(f"[TEST] Erreur: {e}")
                return 1

        # Traitement de toutes les vidéos avec la même config
        for v in selected:
            try:
                outp = process_one_video(v, opts, svcs)
                if outp:
                    print(f"[OK] {v} → {outp}")
            except Exception as e:
                print(f"[ERREUR] {v} → {e}")

        print("\nTerminé.")
        return 0

    else:  # MANUEL
        for v in selected:
            print(f"\n[Manuel] Vidéo : {v}")
            base_opts = build_default_opts()

            v_full = join_input(v)
            aidx = svcs.choose_audio_track(v_full)
            sc = svcs.choose_subtitle_source(v_full)
            if sc is None:
                print("Aucune source de sous-titres choisie.")
                continue
            label = svcs.ask_str("Libellé piste d'origine", base_opts.orig_audio_name or "Original")

            db = ask_float("Réduction (ducking) en dB", base_opts.db_reduct)
            off = ask_int("Décalage ST/TTS (ms, négatif = plus tôt)", base_opts.offset_ms)
            bg = ask_float("Niveau BG (1.0 = inchangé)", base_opts.bg_mix)
            tts = ask_float("Niveau TTS (1.0 = inchangé)", base_opts.tts_mix)

            cur = replace(
                base_opts,
                audio_ffmpeg_index=aidx,
                sub_choice=sc,
                orig_audio_name=(label or "Original"),
                db_reduct=db,
                offset_ms=off,
                bg_mix=bg,
                tts_mix=tts,
            )

            do_test = ask_yes_no("Faire un test de 5 minutes ?", True)
            try:
                outp = process_one_video(
                    v,
                    cur,
                    svcs,
                    limit_duration_sec=(300 if do_test else None),
                    test_prefix=("TEST_" if do_test else ""),
                )
                if outp:
                    print(f"[OK] {v} → {outp}")
            except Exception as e:
                print(f"[ERREUR] {v} → {e}")

        print("\nTerminé.")
        return 0


if __name__ == "__main__":
    from multiprocessing import freeze_support
    freeze_support()
    sys.exit(main())
