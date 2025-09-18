# src/add_dub/__main__.py
import os
import sys
import pyttsx3
from winrt.windows.media.speechsynthesis import SpeechSynthesizer
from time import perf_counter

from add_dub.adapters.ffmpeg import get_track_info
from add_dub.io.fs import ensure_base_dirs, join_input as _join_input
from add_dub.core.subtitles import list_input_videos, resolve_srt_for_video
from add_dub.core.pipeline import process_one_video
from add_dub.core.tts_generate import generate_dub_audio
from add_dub.cli.ui import ask_mode, ask_yes_no, ask_float, ask_int, ask_str
from add_dub.cli.selectors import (
    choose_files,
    choose_audio_track_ffmpeg_index,   # prend un chemin de fichier
    choose_subtitle_source,            # prend un chemin de fichier
)
from add_dub.core.codecs import final_audio_codec_args, subtitle_codec_for_container
from add_dub.config import cfg

# Mémoire des défauts (persistants durant l’exécution)
AUDIO_CODEC_FINAL = cfg.AUDIO_CODEC_FINAL
AUDIO_BITRATE     = cfg.AUDIO_BITRATE

# Étapes 3→9 en mémoire (défauts initiaux tirés de la config)
MEM_AUDIO_INDEX   = None           # 3) piste audio (ffmpeg index)
MEM_SUB_CHOICE    = None           # 4) source des sous-titres (mode + éventuel index)
MEM_ORIG_LANG     = "Original"     # 5) libellé de la piste audio d’origine
MEM_DB_REDUCT     = cfg.DB_REDUCT  # 6) ducking (dB)
MEM_OFFSET_MS     = cfg.OFFSET_STR # 7) décalage (ms)
MEM_BG_MIX        = cfg.BG_MIX     # 8) niveau BG
MEM_TTS_MIX       = cfg.TTS_MIX    # 9) niveau TTS

AUDIO_CODEC_ARGS = final_audio_codec_args(AUDIO_CODEC_FINAL, AUDIO_BITRATE)
SUB_CODEC = subtitle_codec_for_container(AUDIO_CODEC_FINAL)

def _common_kwargs():
    return {
        "db_reduct": MEM_DB_REDUCT,
        "offset_ms": MEM_OFFSET_MS,
        "bg_mix": MEM_BG_MIX,
        "tts_mix": MEM_TTS_MIX,
        "audio_codec_args": AUDIO_CODEC_ARGS,
        "sub_codec": SUB_CODEC,
        "choose_audio_track_fn": choose_audio_track_ffmpeg_index,
        "choose_subtitle_source_fn": choose_subtitle_source,
        "ask_str_fn": ask_str,
        "resolve_srt_for_video_fn": resolve_srt_for_video,
        "generate_dub_audio_fn": generate_dub_audio,
    }

def _detect_french_voice_id_default_old() -> str | None:
    engine = pyttsx3.init()
    try:
        voices = engine.getProperty("voices")
        for voice in voices or []:
            if "fr" in str(getattr(voice, "languages", "")).lower() or "french" in (voice.name or "").lower():
                return voice.id
        return voices[0].id if voices else None
    finally:
        engine.stop()



def _detect_french_voice_id_default() -> str | None:
    voices = list(SpeechSynthesizer.all_voices)
    if not voices:
        return None

    def pick_by_name(fragment: str) -> str | None:
        f = fragment.lower()
        for v in voices:
            if f in (v.display_name or "").lower():
                return v.id
        return None

    # Priorité : Hortense > Julie > Paul
    for needle in ("Hortense", "Julie", "Paul"):
        vid = pick_by_name(needle)
        if vid:
            return vid

    # Ensuite fr-FR, puis fr-*
    for v in voices:
        if (v.language or "").lower() == "fr-fr":
            return v.id
    for v in voices:
        if (v.language or "").lower().startswith("fr-"):
            return v.id

    # Fallback : première voix dispo
    return voices[0].id


def _ask_steps_3_to_9_for_video(video_name: str, *, force_audio_choice: bool = True, force_sub_choice: bool = True):
    """
    Pose les questions des étapes 3→9 pour UNE vidéo, en utilisant les valeurs en mémoire comme défauts.
    Met à jour la mémoire globale selon les réponses.
    """
    global MEM_AUDIO_INDEX, MEM_SUB_CHOICE, MEM_ORIG_LANG
    global MEM_DB_REDUCT, MEM_OFFSET_MS, MEM_BG_MIX, MEM_TTS_MIX

    video_full = _join_input(video_name)

    # 3) Piste audio
    if force_audio_choice or MEM_AUDIO_INDEX is None:
        MEM_AUDIO_INDEX = choose_audio_track_ffmpeg_index(video_full)

    # 4) Source des sous-titres
    if force_sub_choice or MEM_SUB_CHOICE is None:
        MEM_SUB_CHOICE = choose_subtitle_source(video_full)

    # 5) Langue/libellé de l'audio original
    MEM_ORIG_LANG = ask_str("\nLangue de l'audio original (libellé piste)", MEM_ORIG_LANG)

    # 6) Ducking (dB)
    MEM_DB_REDUCT = ask_float("\nRéduction de volume (ducking) en dB", MEM_DB_REDUCT)

    # 7) Décalage ST/TTS (ms)
    MEM_OFFSET_MS = ask_int("\nDécalage ST/TTS en ms (négatif = plus tôt)", MEM_OFFSET_MS)

    # 8) Niveau BG
    MEM_BG_MIX = ask_float("\nNiveau BG (1.0 inchangé)", MEM_BG_MIX)

    # 9) Niveau TTS
    MEM_TTS_MIX = ask_float("\nNiveau TTS (1.0 inchangé)", MEM_TTS_MIX)

def _run_test_then_confirm(video_name: str, voice_id: str) -> bool:
    """
    Test (5 min) sur la vidéo donnée avec les paramètres en mémoire.
    Retourne True si confirmé, False sinon. Supprime la vidéo test si possible.
    """
    try:
        test_out = process_one_video(
            video_name,
            voice_id,
            limit_duration_sec=300,
            test_prefix="TEST_",
            audio_ffmpeg_index=MEM_AUDIO_INDEX,
            sub_choice=MEM_SUB_CHOICE,
            orig_audio_name=MEM_ORIG_LANG,
            **_common_kwargs(),
        )
        print("\nTest terminé. Ouvre la vidéo générée et vérifie.")
        ok = ask_yes_no("OK ? Générer la version complète ?", default_no=False)
        try:
            if test_out and os.path.exists(test_out):
                os.remove(test_out)
                print(f"Vidéo test supprimée : {test_out}")
        except Exception as e:
            print(f"Suppression vidéo test échouée ({e})")
        return ok
    except Exception as e:
        print(f"[ERREUR] Échec du test: {e}")
        return False

def _run_full_once(video_name: str, voice_id: str):
    """
    Lance le pipeline une fois et retourne la sortie (chemin) ou None en cas d'échec.
    """
    try:
        return process_one_video(
            video_name,
            voice_id,
            audio_ffmpeg_index=MEM_AUDIO_INDEX,
            sub_choice=MEM_SUB_CHOICE,
            orig_audio_name=MEM_ORIG_LANG,
            **_common_kwargs(),
        )
    except Exception as e:
        print(f"[ERREUR] Échec traitement: {e}")
        return None

def _run_full_with_sub_retry(video_name: str, voice_id: str):
    """
    Mode AUTO : si l'exécution échoue (ex. SRT manquant/PGS non résolu),
    on revient à l'étape 4 pour CETTE vidéo, on met à jour MEM_SUB_CHOICE,
    puis on relance une seule fois.
    """
    global MEM_SUB_CHOICE
    out = _run_full_once(video_name, voice_id)
    if out:
        return out

    print(f"[AUTO] Échec lié aux sous-titres pour {video_name}. Revenir à l'étape 4.")
    new_choice = choose_subtitle_source(_join_input(video_name))
    if new_choice is not None:
        MEM_SUB_CHOICE = new_choice
        print(f"[AUTO] Source mise à jour pour le lot : {MEM_SUB_CHOICE}")

    # Relance unique
    return _run_full_once(video_name, voice_id)

def main():
    ensure_base_dirs()

    # 1) Choix des vidéos
    candidate_files = list_input_videos()
    selected_files = choose_files(candidate_files)
    if not selected_files:
        print("Aucun fichier sélectionné.")
        sys.exit(1)

    # 2) Mode auto/manuel
    mode = ask_mode()

    # Voix FR par défaut
    french_voice_id_default = _detect_french_voice_id_default()
    if not french_voice_id_default:
        print("Aucune voix trouvée dans le système TTS.")
        sys.exit(1)

    if mode == "auto":
        # Config initiale sur la première vidéo (boucle jusqu’à validation)
        first_video = selected_files[0]
        while True:
            print(f"\n[Auto] Configuration initiale sur : {first_video}")
            _ask_steps_3_to_9_for_video(first_video, force_audio_choice=True, force_sub_choice=True)

            # 10) Test(s) avant lot
            do_test = ask_yes_no("Faire un test 5 minutes ?", default_no=True)
            if do_test:
                ok = _run_test_then_confirm(first_video, french_voice_id_default)
                if not ok:
                    print("\nReprise depuis l’étape 4 (source des sous-titres) avec les valeurs en mémoire.")
                    MEM_SUB_CHOICE = choose_subtitle_source(_join_input(first_video))
                    continue

            # Traitement du lot
            print(f"\nTraitement de {len(selected_files)} vidéo(s) avec la configuration validée.")
            for video_name in selected_files:
                _run_full_with_sub_retry(video_name, french_voice_id_default)
            break  # auto terminé

    else:
        # Mode manuel : inchangé
        for video_name in selected_files:
            print(f"\n[Manuel] Vidéo : {video_name}")
            _ask_steps_3_to_9_for_video(video_name, force_audio_choice=True, force_sub_choice=True)

            do_test = ask_yes_no("Faire un test 5 minutes ?", default_no=True)
            if do_test:
                ok = _run_test_then_confirm(video_name, french_voice_id_default)
                if not ok:
                    print("\nReprise depuis l’étape 4 avec les valeurs en mémoire (cette vidéo).")
                    _ask_steps_3_to_9_for_video(video_name, force_audio_choice=False, force_sub_choice=True)
                    do_test_again = ask_yes_no("Relancer un test 5 minutes ?", default_no=True)
                    if do_test_again:
                        ok = _run_test_then_confirm(video_name, french_voice_id_default)
                        if not ok:
                            print("Paramètres non validés, on passe à la vidéo suivante.")
                            continue

            _run_full_once(video_name, french_voice_id_default)

    print("\nTerminé.")

if __name__ == "__main__":
    from multiprocessing import freeze_support
    freeze_support()
    main()
