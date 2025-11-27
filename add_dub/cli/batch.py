# add_dub/cli/batch.py
from __future__ import annotations

import os
from typing import Iterable, List, Optional, Tuple
from dataclasses import replace

from add_dub.io.fs import ensure_base_dirs, INPUT_DIR, set_base_dirs
from add_dub.core.options import DubOptions
from add_dub.core.pipeline import process_one_video
from add_dub.core.subtitles import (
    list_input_videos,
    resolve_srt_for_video,
    find_sidecar_srt,
    _srt_in_srt_dir_for_video,
)
from add_dub.core.codecs import final_audio_codec_args, subtitle_codec_for_container
from add_dub.core.tts_generate import generate_dub_audio
from add_dub.core.tts_registry import (
    normalize_engine,
    resolve_voice_with_fallbacks,
)
from add_dub.adapters.ffmpeg import get_track_info  # ffprobe
from add_dub.config.opts_loader import load_options
from add_dub.i18n import t

from add_dub.config.effective import effective_values
from add_dub.core.services import Services
import add_dub.io.fs as io_fs

# --------------------------
# Dossiers (batch = sans prompt)
# --------------------------
def _apply_dirs_from_conf() -> None:
    """
    Si options.conf contient input_dir/output_dir/tmp_dir, on les applique.
    Pas d'interaction en mode batch.
    """
    opts = load_options()
    in_dir  = opts.get("input_dir").value  if "input_dir"  in opts else None
    out_dir = opts.get("output_dir").value if "output_dir" in opts else None
    tmp_dir = opts.get("tmp_dir").value   if "tmp_dir"    in opts else None
    if any(v for v in (in_dir, out_dir, tmp_dir)):
        set_base_dirs(in_dir, out_dir, tmp_dir)


# --------------------------
# Ciblage des vidéos
# --------------------------
def _gather_targets(paths: Optional[List[str]], recursive: bool) -> List[str]:
    """
    Construit la liste des vidéos à traiter.
    - Si paths vide -> toutes les vidéos éligibles de INPUT_DIR (voir list_input_videos)
    - Sinon, accepte fichiers/dossiers absolus ou relatifs; peut parcourir récursivement.
    """
    ensure_base_dirs()
    results: List[str] = []

    if not paths:
        for name in list_input_videos():
            results.append(os.path.join(io_fs.INPUT_DIR, name))
        return results

    exts = (".mkv", ".mp4", ".avi", ".mov")
    for p in paths:
        if not p:
            continue
        p = os.path.abspath(p.strip('"'))  # tolère les guillemets passés dans le .bat

        # Fichier vidéo direct
        if os.path.isfile(p) and p.lower().endswith(exts):
            results.append(p)
            continue

        # Dossier
        if os.path.isdir(p):
            if recursive:
                for root, _dirs, files in os.walk(p):
                    for f in files:
                        if f.lower().endswith(exts):
                            results.append(os.path.join(root, f))
            else:
                for f in os.listdir(p):
                    if f.lower().endswith(exts):
                        results.append(os.path.join(p, f))
            continue

        # Nom relatif par rapport à INPUT_DIR (ex: juste "foo.mkv")
        candidate = os.path.join(io_fs.INPUT_DIR, p)
        if os.path.isfile(candidate) and candidate.lower().endswith(exts):
            results.append(candidate)
        elif os.path.isdir(candidate):
            for name in list_input_videos():
                results.append(os.path.join(io_fs.INPUT_DIR, name))

    # Déduplique en préservant l'ordre
    seen = set()
    dedup: List[str] = []
    for x in results:
        if x not in seen:
            seen.add(x)
            dedup.append(x)
    return dedup


# --------------------------
# Services non interactifs
# --------------------------
def _build_services(args):
    """
    Fournit les callbacks nécessaires au pipeline sans interaction.
    - choose_audio_track : index global de la première piste audio (ffprobe).
    - choose_subtitle_source : SRT sidecar prioritaire, sinon piste MKV demandée (défaut 0).
    """
    def _choose_files(files: Iterable[str]) -> List[str]:
        return list(files)

    def _choose_audio_track(input_video_path: str) -> int:
        tracks = get_track_info(input_video_path) or []
        if not tracks:
            return 0
        idx = tracks[0].get("index", 0)
        try:
            return int(idx)
        except Exception:
            return 0

    def _auto_sub_choice(input_video_path: str) -> Optional[Tuple[str, Optional[int]]]:
        try:
            if find_sidecar_srt(input_video_path):
                return ("srt", None)
        except Exception:
            pass
        return ("mkv", 0)

    def _choose_subtitle_source(input_video_path: str):
        mode = (getattr(args, "sub_mode", "auto") or "auto").lower()
        if mode == "srt":
            # Priorité 1 : srt/
            in_srt = _srt_in_srt_dir_for_video(input_video_path)
            if in_srt:
                return ("srt", in_srt)
            # Priorité 2 : sidecar
            sidecar = find_sidecar_srt(input_video_path)
            if sidecar:
                return ("srt", sidecar)
            return ("srt", None)
        if mode == "mkv":
            try:
                idx = max(0, int(getattr(args, "sub_index", 0)))
            except Exception:
                idx = 0
            return ("mkv", idx)
        return _auto_sub_choice(input_video_path)

    return Services(
        resolve_srt_for_video=resolve_srt_for_video,
        generate_dub_audio=generate_dub_audio,
        choose_files=_choose_files,
        choose_audio_track=_choose_audio_track,
        choose_subtitle_source=_choose_subtitle_source,
    )


# --------------------------
# Options
# --------------------------
def _make_options(args) -> DubOptions:
    # Codecs
    audio_args = final_audio_codec_args(args.audio_codec, args.audio_bitrate)
    sub_codec = subtitle_codec_for_container(".mkv")

    # Moteur & voix — lecture silencieuse depuis les valeurs effectives, avec override CLI
    fused = effective_values()  # options.conf > defaults
    engine = normalize_engine(getattr(args, "tts_engine", None) or fused["tts_engine"])

    desired_voice = args.voice or fused.get("voice")
    resolved = resolve_voice_with_fallbacks(
        engine=engine,
        desired_voice_id=desired_voice,
        preferred_lang_base=None  # en batch: on laisse le registre faire ses fallbacks
    )
    if resolved is None:
        raise SystemExit("Aucune voix TTS exploitable (moteur demandé + fallbacks).")

    voice_id = resolved["id"] if isinstance(resolved, dict) else resolved

    return DubOptions(
        audio_ffmpeg_index=args.audio_index,
        sub_choice=None,  # résolu plus tard
        orig_audio_lang=args.orig_audio_lang if hasattr(args, "orig_audio_lang") else "Original",
        db_reduct=args.ducking_db,
        offset_ms=args.offset_ms,
        bg_mix=args.bg_mix,
        tts_mix=args.tts_mix,
        min_rate_tts=args.min_rate_tts,
        max_rate_tts=args.max_rate_tts,
        audio_codec=args.audio_codec,
        audio_bitrate=args.audio_bitrate,
        tts_engine=engine,
        voice_id=voice_id,
        audio_codec_args=audio_args,
        sub_codec=sub_codec,
        offset_video_ms=args.offset_video_ms,
    )

def main(args) -> int:
    # Applique les dossiers depuis options.conf (pas de prompt en batch)
    _apply_dirs_from_conf()
    ensure_base_dirs()

    targets = _gather_targets(args.input, args.recursive)
    if not targets:
        print(t("cli_no_video"))
        return 2

    svcs = _build_services(args)
    opts = _make_options(args)

    any_error = False
    for path in targets:
        print(t("cli_batch_start", path=path))
        if args.dry_run:
            sub_choice = svcs.choose_subtitle_source(path)
            aud_idx = opts.audio_ffmpeg_index if opts.audio_ffmpeg_index is not None else svcs.choose_audio_track(path)
            print(t("cli_sub_choice", choice=sub_choice))
            print(t("cli_audio_index", index=aud_idx))
            print(t("cli_tts_engine", engine=opts.tts_engine))
            print(t("cli_voice", voice=opts.voice_id))
            print(t("cli_codec", codec=opts.audio_codec, bitrate=opts.audio_bitrate))
            print(t("cli_mix", bg_mix=opts.bg_mix, tts_mix=opts.tts_mix, ducking_db=opts.db_reduct))
            print(t("cli_rates", min=opts.min_rate_tts, max=opts.max_rate_tts))
            print(t("cli_offsets", offset=opts.offset_ms, offset_video=opts.offset_video_ms))
            continue

        run_opts = replace(opts)
        if run_opts.audio_ffmpeg_index is None:
            run_opts.audio_ffmpeg_index = svcs.choose_audio_track(path)
        run_opts.sub_choice = svcs.choose_subtitle_source(path)

        out = process_one_video(
            input_video_path=path,
            input_video_name=os.path.basename(path),
            output_dir_path=(args.output_dir or None),
            opts=run_opts,
            svcs=svcs,
            limit_duration_sec=args.limit_duration_sec,
        )
        if not out:
            any_error = True

    return 1 if any_error else 0
