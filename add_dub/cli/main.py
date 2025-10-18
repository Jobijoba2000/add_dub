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
from add_dub.core.tts import is_valid_voice_id, get_system_default_voice_id, list_available_voices
from add_dub.core.subtitles import resolve_srt_for_video

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

opts = load_options()


def build_services() -> Services:
    return Services(
        resolve_srt_for_video=resolve_srt_for_video,
        generate_dub_audio=generate_dub_audio,
        choose_files=choose_files,
        choose_audio_track=choose_audio_track_ffmpeg_index,
        choose_subtitle_source=choose_subtitle_source,
    )


# -------------------------------
# Sélection langue de doublage → voix (identique à ta version)
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
    return sorted(buckets.items(), key=lambda kv: kv[0] or "~")


def _display_name_short(d: str) -> str:
    s = (d or "").strip()
    if s.lower().startswith("microsoft "):
        s = s.split(" ", 1)[1].strip()
    return s or d


def _ask_dub_language_and_voice(default_voice: str | None) -> str | None:
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


def _ask_dirs_if_needed() -> None:
    """
    Si les clés input_dir / output_dir / tmp_dir existent dans options.conf
    **avec le flag 'd'**, on demande en interactif et on applique immédiatement.
    """
    in_entry = opts.get("input_dir")
    out_entry = opts.get("output_dir")
    tmp_entry = opts.get("tmp_dir")

    new_in = None
    new_out = None
    new_tmp = None

    if in_entry and getattr(in_entry, "display", False):
        new_in = ask_option("input_dir", opts, "str", "Dossier d'entrée (input_dir)", in_entry.value)
    if out_entry and getattr(out_entry, "display", False):
        new_out = ask_option("output_dir", opts, "str", "Dossier de sortie (output_dir)", out_entry.value)
    if tmp_entry and getattr(tmp_entry, "display", False):
        new_tmp = ask_option("tmp_dir", opts, "str", "Dossier temporaire (tmp_dir)", tmp_entry.value)

    if any(v is not None for v in (new_in, new_out, new_tmp)):
        set_base_dirs(new_in, new_out, new_tmp)
        # `ensure_base_dirs()` sera appelé juste après dans `main()`


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
            print("Aucune source de sous-titres choisie.")
            return None

    voice_entry = opts.get("voice_id")
    chosen_voice = base_opts.voice_id or None

    if voice_entry and getattr(voice_entry, "display", False):
        maybe_voice = _ask_dub_language_and_voice(default_voice=base_opts.voice_id)
        if maybe_voice:
            chosen_voice = maybe_voice

    if not chosen_voice or not is_valid_voice_id(chosen_voice):
        fallback = get_system_default_voice_id()
        if not fallback:
            try:
                voices = list_available_voices()
                fallback = voices[0]["id"] if voices else None
            except Exception:
                fallback = None
        chosen_voice = fallback

    oal = ask_option("orig_audio_lang", opts, "str", "Langue originale", base_opts.orig_audio_lang)
    db = ask_option("db", opts, "float", "Réduction (ducking) en dB", base_opts.db_reduct)
    off = ask_option("offset", opts, "int", "Décalage ST/TTS (ms, négatif = plus tôt)", base_opts.offset_ms)
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
        orig_audio_lang=oal,
        db_reduct=db,
        offset_ms=off,
        bg_mix=bg,
        tts_mix=tts,
        min_rate_tts=min_rate_tts,
        max_rate_tts=max_rate_tts,
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
                print(f"[OK] {input_video_name} → {outp}")
        except Exception as e:
            print(f"[ERREUR] {input_video_name} → {e}")

    print("\nTerminé.")
    return 0


def main() -> int:
    svcs = build_services()
    while True:
        # 1) Demander d'abord les dossiers si options.conf marque 'd'
        _ask_dirs_if_needed()
        # 2) Créer/valider les dossiers (sans écraser les overrides, cf. flags)
        ensure_base_dirs()

        # Petit log de contrôle des chemins effectifs utilisés (dynamiques)
        print(f"[dirs] input={io_fs.INPUT_DIR} | output={io_fs.OUTPUT_DIR} | tmp={io_fs.TMP_DIR}")

        files = list_input_videos()
        if not files:
            print("Aucun fichier éligible trouvé dans input/.")
            return 1

        selected = svcs.choose_files(files)
        if not selected:
            print("Aucun fichier sélectionné.")
            return 1

        code = run_interactive(selected, svcs)

        choix = input("Voulez-vous générer une autre vidéo ? (o/n) : ").strip().lower()
        if not choix.startswith("o"):
            return code
