# add_dub/cli/main.py
import os
import sys
from dataclasses import replace

import add_dub.io.fs as io_fs  # ← module, pas des valeurs copiées
from add_dub.io.fs import ensure_base_dirs, set_base_dirs, join_input, join_output

from add_dub.core.subtitles import list_input_videos, resolve_srt_for_video
from add_dub.core.pipeline import process_one_video
from add_dub.core.codecs import final_audio_codec_args
from add_dub.core.tts_generate import generate_dub_audio

from add_dub.cli.ui import ask_option
from add_dub.cli.selectors import (
    choose_audio_track_ffmpeg_index,
    choose_files,
    choose_subtitle_source,
)

from add_dub.config import cfg
from add_dub.helpers.time import measure_duration as _md
from add_dub.config.opts_loader import load_options

from add_dub.core.options import DubOptions
from add_dub.core.services import Services
from add_dub.adapters.mkvtoolnix import audio_video_offset_ms

# Builder centralisé (options.conf > defaults.py)
from add_dub.config.effective import build_default_opts

# Registre TTS moteur-agnostique
from add_dub.core.tts_registry import (
    normalize_engine,
    list_voices_for_engine,
    resolve_voice_with_fallbacks,
)
from add_dub.i18n import init_language, t
from add_dub.logger import logger as log

# ---------------------------------------------------------------------------
# Helpers locaux
# ---------------------------------------------------------------------------

def _lang_base(lang_code: str) -> str:
    if not lang_code:
        return ""
    return lang_code.split("-")[0].lower()

def _group_by_lang_base(voices: list[dict]) -> list[tuple[str, list[dict]]]:
    """
    Regroupe une liste de voix par leur langue de base (ex: 'fr', 'en').
    Retourne une liste de tuples (lang_base, [voix...]) triée par lang_base.
    """
    groups = {}
    for v in voices:
        lang = v.get("lang", "")
        base = _lang_base(lang)
        if base not in groups:
            groups[base] = []
        groups[base].append(v)
    
    # On trie les clés (langues)
    sorted_keys = sorted(groups.keys())
    return [(k, groups[k]) for k in sorted_keys]

def _display_name_short(name: str) -> str:
    """
    Nettoie un peu le nom de la voix pour l'affichage (enlève 'Microsoft', etc.)
    """
    # Ex: "Microsoft Guy Online (Natural) - English (United States)"
    # On veut juste "Guy (Natural)"
    s = name
    if "Microsoft " in s:
        s = s.replace("Microsoft ", "")
    if " Online" in s:
        s = s.replace(" Online", "")
    # Souvent la partie après " - " est la langue, on peut la masquer si on l'affiche déjà
    if " - " in s:
        s = s.split(" - ")[0]
    return s.strip()

def _read_index(prompt: str, max_idx: int, default_idx: int = 1) -> int:
    while True:
        raw = input(f"{prompt} [{default_idx}] : ").strip()
        if not raw:
            return default_idx
        if raw.lower() == "q":
            return -1
        try:
            val = int(raw)
            if 1 <= val <= max_idx:
                return val
        except ValueError:
            pass
        print(t("ui_invalid_value"))

def build_services() -> Services:
    return Services(
        resolve_srt_for_video=resolve_srt_for_video,
        generate_dub_audio=generate_dub_audio,
        choose_files=choose_files,
        choose_audio_track=choose_audio_track_ffmpeg_index,
        choose_subtitle_source=choose_subtitle_source,
    )

def _ask_voice_for_engine(engine: str) -> str | None:
    # ...
    all_voices = list_voices_for_engine(engine)
    if not all_voices:
        log.info(t("cli_no_voice"))
        return None

    # Étape 1 — langue de base
    groups = _group_by_lang_base(all_voices)
    print(t("cli_lang_avail"))
    for idx, (base, vs) in enumerate(groups, start=1):
        variants = sorted(set(v["lang"] for v in vs if v.get("lang")))
        label = f"{base} ({', '.join(variants)})" if base else "inconnue"
        print(f"    {idx}. {label}")

    lang_idx = _read_index(t("cli_choose_lang"), len(groups), 1)
    base_lang, voices_in_base = groups[lang_idx - 1]

    # Étape 2 — locale (si plusieurs)
    locales = sorted({v.get("lang") for v in voices_in_base if v.get("lang")})
    chosen_locale = None
    if len(locales) <= 1:
        chosen_locale = locales[0] if locales else ""
    else:
        print(t("cli_variants_avail", lang=base_lang or "(inconnue)"))
        for i, loc in enumerate(locales, start=1):
            print(f"    {i}. {loc}")
        loc_idx = _read_index(t("cli_choose_variant"), len(locales), 1)
        chosen_locale = locales[loc_idx - 1]

    # Filtrer strictement sur la locale retenue
    voices = [v for v in voices_in_base if (v.get("lang") == chosen_locale or not chosen_locale)]

    if not voices:
        # Sécurité : si rien, on retombe sur toutes les voix de la langue de base
        voices = voices_in_base

    # Étape 3 — voix
    print(t("cli_voices_avail"))
    for i, v in enumerate(voices, start=1):
        print(f"    {i}. {_display_name_short(v['display_name'])} | voice_id={v['id']} | lang={v['lang']}")

    k2 = _read_index(t("cli_choose_voice"), len(voices), -1)
    if k2 == -1:
        # Entrée vide → annuler
        return None
    return voices[k2 - 1]["id"]


def _ask_dirs_if_needed(
    ask_input: bool | None = None,
    ask_output: bool | None = None,
    ask_tmp: bool | None = None,
) -> None:
    opts = load_options()
    in_entry = opts.get("input_dir")
    out_entry = opts.get("output_dir")
    tmp_entry = opts.get("tmp_dir")

    want_in = ask_input if ask_input is not None else (in_entry.display if in_entry else False)
    want_out = ask_output if ask_output is not None else (out_entry.display if out_entry else False)
    want_tmp = ask_tmp if ask_tmp is not None else (tmp_entry.display if tmp_entry else False)

    new_in, new_out, new_tmp = None, None, None
    if want_in and in_entry:
        new_in = ask_option("input_dir", opts, "str", t("opt_input_dir"), in_entry.value)
    if want_out and out_entry:
        new_out = ask_option("output_dir", opts, "str", t("opt_output_dir"), out_entry.value)
    if want_tmp and tmp_entry:
        new_tmp = ask_option("tmp_dir", opts, "str", t("opt_tmp_dir"), tmp_entry.value)

    if any(v is not None for v in (new_in, new_out, new_tmp)):
        set_base_dirs(new_in, new_out, new_tmp)


def _ask_engine_and_voice_if_needed(base_opts: DubOptions) -> tuple[str, str | None]:
    opts = load_options()
    engine_entry = opts.get("tts_engine")
    current_engine = base_opts.tts_engine
    if engine_entry and getattr(engine_entry, "display", False):
        print(t("cli_engine_choice"))
        print(t("cli_engine_1"))
        print(t("cli_engine_2"))
        print(t("cli_engine_3"))
        s = input(t("cli_choose_engine")).strip()
        if s == "2":
            current_engine = "edge"
        elif s == "3":
            current_engine = "gtts"
        else:
            current_engine = "onecore"

        chosen_voice = _ask_voice_for_engine(current_engine)
        return current_engine, chosen_voice

    # Pas de 'd' → pas d'interaction ici
    return current_engine, None


def _ask_config_for_video(
    *,
    base_opts: DubOptions,
    svcs: Services,
    input_video_path: str,
    force_choose_tracks_and_subs: bool = True,
) -> DubOptions | None:
    aidx = base_opts.audio_ffmpeg_index
    sc = base_opts.sub_choice

    if force_choose_tracks_and_subs:
        aidx = svcs.choose_audio_track(input_video_path)
        sc = svcs.choose_subtitle_source(input_video_path)
        if sc is None:
            print(t("cli_no_sub_chosen"))
            return None

    # 1) Moteur + (éventuellement) voix si 'd' sur tts_engine
    engine, voice_from_wizard = _ask_engine_and_voice_if_needed(base_opts)

    # 2) Préparer voice_id de départ
    chosen_voice = voice_from_wizard if voice_from_wizard else (base_opts.voice_id or None)

    # 3) Les autres options utilisateur
    opts = load_options()
    oal = ask_option("orig_audio_lang", opts, "str", t("opt_orig_lang"), base_opts.orig_audio_lang)
    db = ask_option("db", opts, "float", t("opt_ducking"), base_opts.db_reduct)
    off = ask_option("offset", opts, "int", t("opt_offset"), base_opts.offset_ms)
    offvid = ask_option("offset_video", opts, "int", t("opt_offset_video"), base_opts.offset_video_ms)
    bg = ask_option("bg", opts, "float", t("opt_bg_mix"), base_opts.bg_mix)
    tts_val = ask_option("tts", opts, "float", t("opt_tts_mix"), base_opts.tts_mix)
    min_rate_tts = ask_option("min_rate_tts", opts, "float", t("opt_min_rate"), base_opts.min_rate_tts)
    max_rate_tts = ask_option("max_rate_tts", opts, "float", t("opt_max_rate"), base_opts.max_rate_tts)
    ac = ask_option("audio_codec", opts, "str", t("opt_codec"), base_opts.audio_codec)
    ab = ask_option("audio_bitrate", opts, "int", t("opt_bitrate"), base_opts.audio_bitrate)

    # 4) Validation & fallbacks (silencieux) selon le moteur choisi
    lang_hint_base = _lang_base(oal) if oal else ""
    chosen_voice = resolve_voice_with_fallbacks(
        engine=engine,
        desired_voice_id=chosen_voice,
        preferred_lang_base=lang_hint_base or None
    )

    if chosen_voice is None:
        print(t("cli_no_voice"))
        return None

    return replace(
        base_opts,
        audio_ffmpeg_index=aidx,
        sub_choice=sc,
        orig_audio_lang=oal,
        db_reduct=db,
        offset_ms=off,
        bg_mix=bg,
        tts_mix=tts_val,
        min_rate_tts=min_rate_tts,
        max_rate_tts=max_rate_tts,
        audio_codec=ac,
        audio_bitrate=ab,
        tts_engine=engine,
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
            print(t("pipeline_test_deleted", path=output_path))
    except Exception as e:
        print(t("pipeline_test_del_err", path=output_path, err=e))


def run_interactive(selected: list[str], svcs: Services) -> int:
    base_for_tests = build_default_opts()

    opts_local = _ask_config_for_video(
        base_opts=base_for_tests,
        svcs=svcs,
        input_video_path=join_input(selected[0]),
        force_choose_tracks_and_subs=True,
    )

    for input_video_name in selected:
        try:
            outp = process_one_video(
                input_video_path=join_input(input_video_name),
                input_video_name=input_video_name,
                opts=opts_local,
                svcs=svcs
            )
            if outp:
                log.info(f"{input_video_name} → {outp}")
        except Exception as e:
            print(t("cli_error", msg=f"{input_video_name} → {e}"))

    print(t("cli_done"))
    return 0


def main() -> int:
    init_language()
    svcs = build_services()
    while True:
        # 1) Demander d'abord les dossiers si options.conf marque 'd'
        _ask_dirs_if_needed()
        # 2) Créer/valider les dossiers (sans écraser les overrides, cf. flags)

        while True:
            ensure_base_dirs()

            # Petit log de contrôle des chemins effectifs utilisés (dynamiques)
            print(t("cli_dirs", input=io_fs.INPUT_DIR, output=io_fs.OUTPUT_DIR, tmp=io_fs.TMP_DIR))

            files = list_input_videos()
            if files:
                break  # OK → on sort de la boucle et on continue le flux normal

            # Aucun fichier exploitable → mini-menu
            log.error("Aucun fichier éligible trouvé dans %s", io_fs.INPUT_DIR)
            print(t("cli_no_eligible_short"))
            print(t("cli_help_formats"))
            print(t("cli_help_input"))
            print(t("cli_menu_title"))
            print(t("cli_menu_change_input"))
            print(t("cli_menu_help"))
            print(t("cli_menu_rescan"))
            print(t("cli_menu_quit"))

            choice = input(t("cli_input_choice")).strip() or "3"

            if choice == "1":
                new_in = input(t("cli_new_input")).strip()
                if new_in:
                    # Applique uniquement l'input_dir, laisse output/tmp inchangés
                    set_base_dirs(new_in, None, None)
                    log.info("Dossier d'entrée changé vers: %s", new_in)
                    print(t("cli_input_changed", path=new_in))
                continue  # on re-scannera au prochain tour

            if choice == "2":
                print(t("cli_help_details"))
                input(t("cli_press_enter"))
                continue

            if choice == "3":
                # Relancer le scan sans rien changer
                continue

            if choice == "4":
                return 1

            # Entrée invalide → on re-tente
            print(t("cli_invalid_choice"))
            continue

        selected = svcs.choose_files(files)
        if not selected:
            print(t("cli_no_selection"))
            return 1

        code = run_interactive(selected, svcs)

        choix = input(t("cli_ask_another")).strip().lower()
        if not choix.startswith("o") and not choix.startswith("y") and not choix.startswith("s") and not choix.startswith("j"):
            return code
