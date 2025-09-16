# src/add_dub/__main__.py
import os
import sys
import pyttsx3

from add_dub.adapters.ffmpeg import get_track_info
from add_dub.adapters.mkvtoolnix import list_mkv_sub_tracks
from add_dub.core.subtitles import find_sidecar_srt, list_input_videos, resolve_srt_for_video
from add_dub.io.fs import ensure_base_dirs, join_input as _join_input
from add_dub.core.pipeline import process_one_video
from add_dub.core.tts_generate import generate_dub_audio
from add_dub.cli.ui import ask_mode, ask_yes_no, ask_float, ask_int, ask_str
from add_dub.cli.selectors import (
    choose_files,
    choose_audio_track_ffmpeg_index,
    choose_subtitle_source,
)
from add_dub.core.codecs import final_audio_codec_args, subtitle_codec_for_container
from add_dub.config import cfg

# copies mutables pour la session (modifiées par les questions utilisateur)
AUDIO_CODEC_FINAL = cfg.AUDIO_CODEC_FINAL
AUDIO_BITRATE     = cfg.AUDIO_BITRATE
BG_MIX            = cfg.BG_MIX
TTS_MIX           = cfg.TTS_MIX
DB_REDUCT         = cfg.DB_REDUCT
OFFSET_STR        = cfg.OFFSET_STR

AUDIO_CODEC_ARGS = final_audio_codec_args(AUDIO_CODEC_FINAL, AUDIO_BITRATE)
SUB_CODEC = subtitle_codec_for_container(AUDIO_CODEC_FINAL)


def main():
    ensure_base_dirs()

    global BG_MIX, TTS_MIX, DB_REDUCT, OFFSET_STR

    candidate_files = list_input_videos()
    selected_files = choose_files(candidate_files)
    if not selected_files:
        print("Aucun fichier sélectionné.")
        sys.exit(1)

    mode = ask_mode()

    # Détection voix FR
    engine = pyttsx3.init()
    voices = engine.getProperty("voices")
    french_voice_id_default = None
    for voice in voices:
        if "fr" in str(voice.languages).lower() or "french" in voice.name.lower():
            french_voice_id_default = voice.id
            break
    if not french_voice_id_default and voices:
        print("Aucune voix FR trouvée, utilisation de la voix par défaut.")
        french_voice_id_default = voices[0].id
    engine.stop()

    if mode == "auto":
        # Réglages communs (une seule fois)
        DB_REDUCT = ask_float("\nRéduction de volume (ducking) en dB", DB_REDUCT)
        OFFSET_STR = ask_int("\nDécalage ST/TTS en ms (négatif = plus tôt)", OFFSET_STR)
        BG_MIX = ask_float("\nNiveau BG (1.0 inchangé)", BG_MIX)
        TTS_MIX = ask_float("\nNiveau TTS (1.0 inchangé)", TTS_MIX)

        # Sélection unique sur la première vidéo : piste audio + source sous-titres + nom piste
        first_video = selected_files[0]
        first_full = _join_input(first_video)
        print(f"\n[AUTO] Configuration sur la première vidéo : {first_video}")

        audio_ffmpeg_index_global = choose_audio_track_ffmpeg_index(first_full)
        sub_choice_global = choose_subtitle_source(first_full)
        if sub_choice_global is None:
            print("[AUTO] Pas de sous-titre détecté sur la première vidéo. Arrêt.")
            sys.exit(1)
        orig_audio_name_global = ask_str("\nNom de la piste audio d'origine (ex. Japonais)", "Original")

        print(f"\n[AUTO] Configuration verrouillée. Traitement de {len(selected_files)} vidéo(s) sans autre question.")
        for video_name in selected_files:
            process_one_video(
                video_name,
                french_voice_id_default,
                audio_ffmpeg_index=audio_ffmpeg_index_global,
                sub_choice=sub_choice_global,
                orig_audio_name=orig_audio_name_global,
                db_reduct=DB_REDUCT,
                offset_ms=OFFSET_STR,
                bg_mix=BG_MIX,
                tts_mix=TTS_MIX,
                audio_codec_args=AUDIO_CODEC_ARGS,
                sub_codec=SUB_CODEC,
                choose_audio_track_fn=choose_audio_track_ffmpeg_index,
                choose_subtitle_source_fn=choose_subtitle_source,
                ask_str_fn=ask_str,
                resolve_srt_for_video_fn=resolve_srt_for_video,
                generate_dub_audio_fn=generate_dub_audio,
            )

    else:
        for video_name in selected_files:
            print(f"\n===== Vidéo : {video_name} =====")
            local_db = DB_REDUCT
            local_off = OFFSET_STR
            local_bg = BG_MIX
            local_tts = TTS_MIX

            while True:
                print("(Entrée pour conserver la valeur entre crochets)")
                local_db = ask_float("Réduction de volume (dB)", local_db)
                local_off = ask_int("Décalage ST/TTS (ms)", local_off)
                local_bg = ask_float("Niveau BG (1.0 inchangé)", local_bg)
                local_tts = ask_float("Niveau TTS (1.0 inchangé)", local_tts)

                DB_REDUCT = local_db
                OFFSET_STR = local_off
                BG_MIX = local_bg
                TTS_MIX = local_tts

                want_test = ask_yes_no("Faire un test 5 minutes ?", default_no=True)
                if want_test:
                    test_out = process_one_video(
                        video_name,
                        french_voice_id_default,
                        limit_duration_sec=300,
                        test_prefix="TEST_",
                        db_reduct=DB_REDUCT,
                        offset_ms=OFFSET_STR,
                        bg_mix=BG_MIX,
                        tts_mix=TTS_MIX,
                        audio_codec_args=AUDIO_CODEC_ARGS,
                        sub_codec=SUB_CODEC,
                        choose_audio_track_fn=choose_audio_track_ffmpeg_index,
                        choose_subtitle_source_fn=choose_subtitle_source,
                        ask_str_fn=ask_str,
                        resolve_srt_for_video_fn=resolve_srt_for_video,
                        generate_dub_audio_fn=generate_dub_audio,
                    )
                    print("\nTest terminé. Ouvre la vidéo générée et vérifie.")
                    ok = ask_yes_no("OK ? Générer la version complète ?", default_no=False)
                    try:
                        if test_out and os.path.exists(test_out):
                            os.remove(test_out)
                            print(f"Vidéo test supprimée : {test_out}")
                    except Exception as e:
                        print(f"Suppression vidéo test échouée ({e})")

                    if ok:
                        process_one_video(
                            video_name,
                            french_voice_id_default,
                            db_reduct=DB_REDUCT,
                            offset_ms=OFFSET_STR,
                            bg_mix=BG_MIX,
                            tts_mix=TTS_MIX,
                            audio_codec_args=AUDIO_CODEC_ARGS,
                            sub_codec=SUB_CODEC,
                            choose_audio_track_fn=choose_audio_track_ffmpeg_index,
                            choose_subtitle_source_fn=choose_subtitle_source,
                            ask_str_fn=ask_str,
                            resolve_srt_for_video_fn=resolve_srt_for_video,
                            generate_dub_audio_fn=generate_dub_audio,
                        )
                        break
                    else:
                        print("On refait un test avec d'autres options.")
                        continue
                else:
                    process_one_video(
                        video_name,
                        french_voice_id_default,
                        db_reduct=DB_REDUCT,
                        offset_ms=OFFSET_STR,
                        bg_mix=BG_MIX,
                        tts_mix=TTS_MIX,
                        audio_codec_args=AUDIO_CODEC_ARGS,
                        sub_codec=SUB_CODEC,
                        choose_audio_track_fn=choose_audio_track_ffmpeg_index,
                        choose_subtitle_source_fn=choose_subtitle_source,
                        ask_str_fn=ask_str,
                        resolve_srt_for_video_fn=resolve_srt_for_video,
                        generate_dub_audio_fn=generate_dub_audio,
                    )
                    break

    print("\nTerminé.")

if __name__ == "__main__":
    from multiprocessing import freeze_support
    freeze_support()
    main()
