# add_dub/cli/main.py
import os
import sys
from dataclasses import replace

from add_dub.io.fs import ensure_base_dirs, join_input
from add_dub.core.subtitles import list_input_videos, resolve_srt_for_video
from add_dub.core.pipeline import process_one_video
from add_dub.core.options import DubOptions, Services
from add_dub.core.tts_generate import generate_dub_audio
from add_dub.cli.ui import ask_option, ask_mode, ask_yes_no
from add_dub.cli.selectors import (
    choose_files,
    choose_audio_track_ffmpeg_index,
    choose_subtitle_source,
)
from add_dub.core.codecs import final_audio_codec_args, subtitle_codec_for_container
from add_dub.config import cfg
from add_dub.helpers.time import measure_duration as _md
from add_dub.config.opts_loader import load_options

# NOUVEAU : on importe juste la liste des voix depuis tts.py
from add_dub.core.tts import list_available_voices
from add_dub.core.tts import is_valid_voice_id, get_system_default_voice_id, list_available_voices

opts = load_options()


def _generate_dub_audio_impl(
    *,
    srt_file: str,
    output_wav: str,
    opts: DubOptions,
    duration_limit_sec: int | None,
    target_total_duration_ms: int | None,
) -> str:
    return generate_dub_audio(
        srt_file,
        output_wav,
        opts,
        duration_limit_sec=duration_limit_sec,
        target_total_duration_ms=target_total_duration_ms,
    )


def build_services() -> Services:
    return Services(
        resolve_srt_for_video=resolve_srt_for_video,
        generate_dub_audio=_generate_dub_audio_impl,
        choose_audio_track=choose_audio_track_ffmpeg_index,
        choose_subtitle_source=choose_subtitle_source,
    )


def build_default_opts() -> DubOptions:
    audio_codec = str(opts["audio_codec"].value) if "audio_codec" in opts else cfg.AUDIO_CODEC_FINAL
    audio_bitrate = int(opts["audio_bitrate"].value) if "audio_bitrate" in opts else cfg.AUDIO_BITRATE
    audio_args = final_audio_codec_args(audio_codec, f"{audio_bitrate}k")
    sub_codec = subtitle_codec_for_container(cfg.AUDIO_CODEC_FINAL)
    
    if "voice_id" in opts:
        if not is_valid_voice_id(str(opts["voice_id"].value)):
            opts["voice_id"].display = True
        voice_id = opts["voice_id"].value 
    else:
        voice_id = cfg.VOICE_ID
        

    return DubOptions(
        audio_ffmpeg_index=None,
        sub_choice=None,
        orig_audio_lang=opts["orig_audio_lang"].value if "orig_audio_lang" in opts else cfg.ORIG_AUDIO_LANG,
        db_reduct=float(opts["db"].value) if "db" in opts else cfg.DB_REDUCT,
        offset_ms=int(opts["offset"].value) if "offset" in opts else cfg.OFFSET_STR,
        bg_mix=float(opts["bg"].value) if "bg" in opts else cfg.BG_MIX,
        tts_mix=float(opts["tts"].value) if "tts" in opts else cfg.TTS_MIX,
        min_rate_tts=float(opts["min_rate_tts"].value) if "min_rate_tts" in opts else cfg.MIN_RATE_TTS,
        max_rate_tts=float(opts["max_rate_tts"].value) if "max_rate_tts" in opts else cfg.MAX_RATE_TTS,
        audio_codec=audio_codec,
        audio_bitrate=audio_bitrate,
        voice_id = voice_id,
        audio_codec_args=tuple(audio_args),
        sub_codec=sub_codec,
        offset_video_ms=int(opts["offset_video"].value) if "offset_video" in opts else cfg.OFFSET_VIDEO,
    )


# -------------------------------
# Sélection langue de doublage → voix (AJOUT)
# -------------------------------

def _lang_base(tag: str | None) -> str:
    if not tag:
        return ""
    tag = tag.strip()
    if not tag:
        return ""
    return tag.split("-")[0].lower()


def _group_by_lang_base(voices: list[dict]) -> list[tuple[str, list[dict]]]:
    buckets: dict[str, list[dict]] = {}
    for v in voices:
        b = _lang_base(v.get("lang"))
        buckets.setdefault(b, []).append(v)
    # tri par code
    return sorted(buckets.items(), key=lambda kv: kv[0] or "~")


def _display_name_short(d: str) -> str:
    s = (d or "").strip()
    if s.lower().startswith("microsoft "):
        s = s.split(" ", 1)[1].strip()
    return s or d


def _ask_dub_language_and_voice(default_voice: str | None) -> str | None:
    """
    Affiche les langues détectées (par numéro), puis les voix (prénom + ID complet).
    Retourne l'ID complet de la voix choisie, ou None.
    """
    all_voices = list_available_voices()
    if not all_voices:
        print("[INFO] Aucune voix OneCore détectée.")
        print("Installez des voix : Paramètres Windows → Heure et langue → Voix → Gérer les voix → Ajouter des voix.")
        return None

    groups = _group_by_lang_base(all_voices)
    if not groups:
        print("[INFO] Aucune langue détectée. Liste brute :")
        for i, v in enumerate(all_voices, start=1):
            print(f"    {i}. {_display_name_short(v['display_name'])} | voice_id={v['id']} | lang={v['lang']}")
        s = input("Saisir le numéro de la voix (ou Entrée pour annuler) : ").strip()
        if not s.isdigit():
            return None
        k = int(s)
        if 1 <= k <= len(all_voices):
            return all_voices[k - 1]["id"]
        return None

    print("\nLangues TTS disponibles :")
    for idx, (base, vs) in enumerate(groups, start=1):
        variants = sorted(set(v["lang"] for v in vs if v.get("lang")))
        label = f"{base} ({', '.join(variants)})" if base else "inconnue"
        print(f"    {idx}. {label}")

    s = input("Saisir le numéro de la langue [1] : ").strip()
    lang_idx = int(s) if s.isdigit() else 1
    if not (1 <= lang_idx <= len(groups)):
        lang_idx = 1

    _base, voices = groups[lang_idx - 1]

    print("\nVoix disponibles :")
    for i, v in enumerate(voices, start=1):
        print(f"    {i}. {_display_name_short(v['display_name'])} | voice_id={v['id']} | lang={v['lang']}")

    s2 = input("Saisir le numéro de la voix (ou Entrée pour annuler) : ").strip()
    if not s2.isdigit():
        return None
    k2 = int(s2)
    if 1 <= k2 <= len(voices):
        return voices[k2 - 1]["id"]
    return None


def _ask_config_for_video(
    *,
    base_opts: DubOptions,
    svcs: Services,
    video_fullpath: str,
    force_choose_tracks_and_subs: bool = True,
) -> DubOptions | None:
    aidx = base_opts.audio_ffmpeg_index
    sc = base_opts.sub_choice

    if force_choose_tracks_and_subs:
        aidx = svcs.choose_audio_track(video_fullpath)
        sc = svcs.choose_subtitle_source(video_fullpath)
        if sc is None:
            print("Aucune source de sous-titres choisie.")
            return None

    # --- Sélection VOIX de doublage (garantie d'un voice_id valide) ---
    voice_entry = opts.get("voice_id")
    chosen_voice = base_opts.voice_id or None

    # Si l’option est marquée interactive, on demande la langue puis la voix.
    if voice_entry and getattr(voice_entry, "display", False):
        maybe_voice = _ask_dub_language_and_voice(default_voice=base_opts.voice_id)
        if maybe_voice:
            chosen_voice = maybe_voice

    # Si toujours vide ou invalide, on applique des fallbacks robustes.
    if not chosen_voice or not is_valid_voice_id(chosen_voice):
        fallback = get_system_default_voice_id()
        if not fallback:
            try:
                voices = list_available_voices()
                fallback = voices[0]["id"] if voices else None
            except Exception:
                fallback = None
        chosen_voice = fallback

    # chosen_voice peut rester None si aucune voix système n’est disponible,
    # mais dans ce cas pipeline appliquera quand même un tag par défaut "fr".

    # --- Reste des options (inchangées) ---
    oal = ask_option("orig_audio_lang", opts, "str", "Langue originale", base_opts.orig_audio_lang)
    db = ask_option("db", opts, "float", "Réduction (ducking) en dB", base_opts.db_reduct)
    off    = ask_option("offset", opts, "int", "Décalage ST/TTS (ms, négatif = plus tôt)", base_opts.offset_ms)
    offvid = ask_option("offset_video", opts, "int", "Décalage vidéo (ms, négatif = plus tôt)", base_opts.offset_video_ms)
    bg = ask_option("bg", opts, "float", "Niveau BG (1.0 = inchangé)", base_opts.bg_mix)
    tts = ask_option("tts", opts, "float", "Niveau TTS (1.0 = inchangé)", base_opts.tts_mix)
    min_rate_tts = ask_option("min_rate_tts", opts, "float", "Vitesse TTS minimal (1.0 = inchangé)", base_opts.min_rate_tts)
    max_rate_tts = ask_option("max_rate_tts", opts, "float", "Vitesse TTS maximal (1.8 = inchangé)", base_opts.max_rate_tts)
    ac = ask_option("audio_codec", opts, "str", "Codec audio", base_opts.audio_codec)
    ab = ask_option("audio_bitrate", opts, "int", "Bitrate", base_opts.audio_bitrate)

    return replace(
        base_opts,
        audio_ffmpeg_index=aidx,
        sub_choice=sc,
        orig_audio_lang=oal,  # on ne modifie pas la langue d’origine
        db_reduct=db,
        offset_ms=off,
        bg_mix=bg,
        tts_mix=tts,
        min_rate_tts = min_rate_tts,
        max_rate_tts = max_rate_tts,
        audio_codec=ac,
        audio_bitrate=ab,
        voice_id=chosen_voice,
        audio_codec_args=final_audio_codec_args(ac, f"{ab}k"),
        offset_video_ms=offvid,
    )


def _cleanup_test_outputs(output_path: str | None) -> None:
    if not output_path:
        return
    try:
        if os.path.isfile(output_path):
            os.remove(output_path)
            print(f"[TEST] Fichier supprimé : {output_path}")
    except Exception as e:
        print(f"[TEST] Impossible de supprimer le fichier de test ({output_path}) : {e}")


def run_auto(selected: list[str], svcs: Services) -> int:
    print("\n[Auto] Configuration/test sur la première vidéo, application au lot si validé.")
    first = selected[0]
    first_full = join_input(first)

    base_for_tests = build_default_opts()
    validated_opts = None

    if ask_yes_no("Faire un test de 5 minutes ?", True):
        while True:
            cfg_opts = _ask_config_for_video(
                base_opts=base_for_tests,
                svcs=svcs,
                video_fullpath=first_full,
                force_choose_tracks_and_subs=True,
            )
            if cfg_opts is None:
                return 1

            out_test = None
            try:
                out_test = _md(
                    process_one_video,
                    first,
                    cfg_opts,
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
                validated_opts = cfg_opts
                break
            else:
                print(cfg_opts)
                base_for_tests = replace(
                    cfg_opts,
                    audio_ffmpeg_index=None,
                    sub_choice=None,
                )
    else:
        cfg_opts = _ask_config_for_video(
            base_opts=base_for_tests,
            svcs=svcs,
            video_fullpath=first_full,
            force_choose_tracks_and_subs=True,
        )
        if cfg_opts is None:
            return 1
        validated_opts = cfg_opts

    for v in selected:
        try:
            outp = _md(process_one_video, v, validated_opts, svcs)
            if outp:
                print(f"[OK] {v} → {outp}")
        except Exception as e:
            print(f"[ERREUR] {v} → {e}")

    print("\nTerminé.")
    return 0


def run_manual(selected: list[str], svcs: Services) -> int:
    print("\n[Manuel] Chaque vidéo repart de zéro. Les défauts ne sont conservés que pendant les re-tests de la même vidéo (hors audio/ST).")

    for v in selected:
        print(f"\n[Manuel] Vidéo : {v}")
        v_full = join_input(v)

        base_for_this_video = build_default_opts()

        cur = _ask_config_for_video(
            base_opts=base_for_this_video,
            svcs=svcs,
            video_fullpath=v_full,
            force_choose_tracks_and_subs=True,
        )
        if cur is None:
            print("Aucune source de sous-titres choisie. Vidéo ignorée.")
            continue

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

        if cur is None:
            print("Configuration annulée pour cette vidéo.")
            continue

        try:
            outp = _md(process_one_video, v, cur, svcs)
            if outp:
                print(f"[OK] {v} → {outp}")
        except Exception as e:
            print(f"[ERREUR] {v} → {e}")

    print("\nTerminé.")
    return 0


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
        if mode.startswith("a"):
            code = run_auto(selected, svcs)
        else:
            code = run_manual(selected, svcs)
        choix = input("Voulez-vous générer une autre vidéo ? (o/n) : ").strip().lower()
        if not choix.startswith("o"):
            return code
