# add_dub/gui/server.py
from __future__ import annotations

import os
import sys
import time
import json
import queue
import threading
import urllib.parse
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import replace

import add_dub.io.fs as io_fs
from add_dub.config.effective import effective_values
from add_dub.core.options import DubOptions
from add_dub.core.services import Services
from add_dub.core.tts_registry import (
    normalize_engine,
    list_voices_for_engine,
    resolve_voice_with_fallbacks,
)
from add_dub.core.pipeline import process_one_video
from add_dub.core.codecs import final_audio_codec_args, subtitle_codec_for_container
from add_dub.core.tts_generate import generate_dub_audio


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class AppState:
    def __init__(self):
        self.is_running = False
        self.worker_thread: Optional[threading.Thread] = None
        self.event_queues: List[queue.Queue] = []
        self._lock = threading.Lock()
        self.last_heartbeat = time.time()
        self.client_connected = False
        self.should_exit = False

    def touch_heartbeat(self):
        with self._lock:
            self.last_heartbeat = time.time()
            self.client_connected = True

    def add_event_listener(self) -> queue.Queue:
        q: queue.Queue = queue.Queue()
        with self._lock:
            self.event_queues.append(q)
            self.last_heartbeat = time.time()
            self.client_connected = True
        return q

    def remove_event_listener(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self.event_queues:
                self.event_queues.remove(q)

    def broadcast(self, event_type: str, data: Any) -> None:
        payload = json.dumps({"type": event_type, "data": data}, ensure_ascii=False)
        with self._lock:
            for q in list(self.event_queues):
                try:
                    q.put_nowait(payload)
                except Exception:
                    pass


GLOBAL_STATE = AppState()


class ServerUIAdapter:
    """
    Implémentation de UIInterface qui diffuse en direct les messages,
    erreurs et pourcentages aux clients connectés via Server-Sent Events (SSE).
    """
    def __init__(self, state: AppState):
        self.state = state

    def message(self, text: str) -> None:
        clean = str(text).strip()
        if clean:
            self.state.broadcast("log", clean)
            self.state.broadcast("status", clean[:90])

    def error(self, text: str) -> None:
        clean = str(text).strip()
        if clean:
            self.state.broadcast("error", clean)
            self.state.broadcast("status", "Erreur : " + clean[:80])

    def progress(self, percent: float) -> None:
        pct = max(0.0, min(100.0, float(percent)))
        self.state.broadcast("progress", pct)

    def ask_yes_no(self, question: str, default: bool = False) -> bool:
        self.state.broadcast("log", f"[Confirmation automatique] {question} -> {'Oui' if default else 'Non'}")
        return default

    def ask_float(self, prompt: str, default: float) -> float:
        return float(default)


LANGUAGE_NAMES: Dict[str, str] = {
    "fr": "Français",
    "en": "Anglais",
    "es": "Espagnol",
    "de": "Allemand",
    "it": "Italien",
    "pt": "Portugais",
    "ja": "Japonais",
    "zh": "Chinois",
    "ru": "Russe",
    "ar": "Arabe",
    "nl": "Néerlandais",
    "pl": "Polonais",
    "ko": "Coréen",
    "tr": "Turc",
    "uk": "Ukrainien",
    "sv": "Suédois",
    "cs": "Tchèque",
    "el": "Grec",
    "da": "Danois",
    "fi": "Finnois",
    "no": "Norvégien",
    "hi": "Hindi",
    "vi": "Vietnamien",
    "id": "Indonésien",
    "th": "Thaï",
    "ro": "Roumain",
    "hu": "Hongrois",
}

REGION_NAMES: Dict[str, str] = {
    "FR": "France",
    "CA": "Canada",
    "BE": "Belgique",
    "CH": "Suisse",
    "US": "États-Unis",
    "GB": "Royaume-Uni",
    "AU": "Australie",
    "ES": "Espagne",
    "MX": "Mexique",
    "DE": "Allemagne",
    "AT": "Autriche",
    "IT": "Italie",
    "BR": "Brésil",
    "PT": "Portugal",
    "JP": "Japon",
    "CN": "Chine",
    "TW": "Taïwan",
    "RU": "Russie",
    "IN": "Inde",
    "NL": "Pays-Bas",
    "PL": "Pologne",
    "KR": "Corée",
    "TR": "Turquie",
    "UA": "Ukraine",
    "SE": "Suède",
    "CZ": "Tchéquie",
    "GR": "Grèce",
    "DK": "Danemark",
    "FI": "Finlande",
    "NO": "Norvège",
    "RO": "Roumanie",
    "HU": "Hongrie",
    "VN": "Vietnam",
    "ID": "Indonésie",
    "TH": "Thaïlande",
    "SA": "Arabie Saoudite",
    "EG": "Égypte",
}


def clean_voice_display_name(raw_disp: str, vid: str) -> str:
    import re
    m = re.search(r'\((?:[a-zA-Z\-]+,\s*)?([a-zA-Z0-9]+)\)', raw_disp)
    if m:
        name = m.group(1)
    else:
        name = raw_disp or vid

    name = re.sub(r'Neural$', ' (Neural)', name)
    name = re.sub(r'Multilingual', ' Multilingual', name)
    return name.strip()


class ApiRequestHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        GLOBAL_STATE.touch_heartbeat()
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
            self._serve_static_file("index.html", "text/html; charset=utf-8")
        elif path == "/static/style.css":
            self._serve_static_file("style.css", "text/css; charset=utf-8")
        elif path == "/static/app.js":
            self._serve_static_file("app.js", "application/javascript; charset=utf-8")
        elif path == "/api/options":
            self._handle_get_options()
        elif path == "/api/voices":
            qs = urllib.parse.parse_qs(parsed.query)
            engine = qs.get("engine", ["onecore"])[0]
            self._handle_get_voices(engine)
        elif path == "/api/events":
            self._handle_sse_events()
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        GLOBAL_STATE.touch_heartbeat()
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/heartbeat":
            self._send_json({"status": "ok"})
        elif path == "/api/shutdown":
            GLOBAL_STATE.should_exit = True
            self._send_json({"status": "bye"})
        elif path == "/api/browse-file":
            self._handle_browse_file()
        elif path == "/api/browse-folder":
            self._handle_browse_folder()
        elif path == "/api/test-voice":
            self._handle_test_voice()
        elif path == "/api/run":
            self._handle_run()
        elif path == "/api/stop":
            self._handle_stop()
        else:
            self.send_error(404, "Not Found")

    def _serve_static_file(self, filename: str, content_type: str):
        static_dir = os.path.join(os.path.dirname(__file__), "static")
        filepath = os.path.join(static_dir, filename)
        if not os.path.isfile(filepath):
            self.send_error(404, "Fichier statique introuvable")
            return

        with open(filepath, "rb") as f:
            content = f.read()

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(content)

    def _send_json(self, data: Any, status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> Dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > 0:
                raw = self.rfile.read(length).decode("utf-8")
                return json.loads(raw)
        except Exception:
            pass
        return {}

    def _handle_get_options(self):
        f = effective_values()
        data = {
            "input_dir": io_fs.join_input(""),
            "output_dir": io_fs.join_output(""),
            "tts_engine": normalize_engine(f.get("tts_engine", "onecore")),
            "voice_id": f.get("voice_id", ""),
            "min_rate_tts": float(f.get("min_rate_tts", 1.2)),
            "max_rate_tts": float(f.get("max_rate_tts", 1.8)),
            "ducking_db": float(f.get("ducking_db", f.get("db", -5.0))),
            "bg_mix": float(f.get("bg_mix", f.get("bg", 1.0))),
            "tts_mix": float(f.get("tts_mix", f.get("tts", 1.0))),
            "offset_ms": int(f.get("offset_ms", f.get("offset", 0))),
            "offset_video_ms": int(f.get("offset_video_ms", f.get("offset_video", 0))),
            "audio_codec": str(f.get("audio_codec", "ac3")).lower(),
            "audio_bitrate": str(f.get("audio_bitrate", "256")).replace("k", ""),
            "orig_audio_lang": str(f.get("orig_audio_lang", "Original")),
            "translate": bool(f.get("translate", False)),
            "translate_to": str(f.get("translate_to", "fr")),
            "translate_from": str(f.get("translate_from", "auto")),
            "reuse_translated_subs": bool(f.get("reuse_translated_subs", True)),
            "preserve_tree": bool(f.get("preserve_tree", False)),
            "is_running": GLOBAL_STATE.is_running,
        }
        self._send_json(data)

    def _handle_get_voices(self, engine: str):
        eng = normalize_engine(engine)
        try:
            voices = list_voices_for_engine(eng)
        except Exception:
            voices = []

        lang_set = set()
        regions_by_lang: Dict[str, List[Dict[str, str]]] = {}
        voices_by_region: Dict[str, List[Dict[str, str]]] = {}
        seen_regions = set()

        for v in voices:
            loc = (v.get("lang") or "fr-FR").replace("_", "-")
            parts = loc.split("-")
            base_lang = parts[0].lower()
            region_code = parts[1].upper() if len(parts) > 1 else base_lang.upper()
            full_region = f"{base_lang}-{region_code}"

            lang_set.add(base_lang)

            if base_lang not in regions_by_lang:
                regions_by_lang[base_lang] = []

            if full_region not in seen_regions:
                seen_regions.add(full_region)
                reg_name = REGION_NAMES.get(region_code, region_code)
                regions_by_lang[base_lang].append({
                    "code": full_region,
                    "name": f"{reg_name} ({full_region})"
                })

            if full_region not in voices_by_region:
                voices_by_region[full_region] = []

            raw_disp = v.get("display_name") or v.get("id") or "Inconnue"
            clean_disp = clean_voice_display_name(raw_disp, v.get("id", ""))

            voices_by_region[full_region].append({
                "id": v.get("id", ""),
                "display_name": clean_disp,
                "lang": full_region,
            })

        def lang_sort_key(code: str) -> tuple:
            if code == "fr":
                return (0, "")
            if code == "en":
                return (1, "")
            if code == "es":
                return (2, "")
            name = LANGUAGE_NAMES.get(code, code)
            return (3, name)

        sorted_lang_codes = sorted(list(lang_set), key=lang_sort_key)
        languages = [
            {"code": c, "name": f"{LANGUAGE_NAMES.get(c, c.upper())} ({c})"}
            for c in sorted_lang_codes
        ]

        self._send_json({
            "engine": eng,
            "languages": languages,
            "regions_by_lang": regions_by_lang,
            "voices_by_region": voices_by_region,
        })

    def _handle_browse_file(self):
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        filename = filedialog.askopenfilename(
            title="Sélectionner une vidéo",
            filetypes=[("Fichiers Vidéo", "*.mkv *.mp4 *.avi"), ("Tous les fichiers", "*.*")],
            parent=root,
        )
        root.destroy()
        self._send_json({"path": os.path.normpath(filename) if filename else ""})

    def _handle_browse_folder(self):
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        folder = filedialog.askdirectory(title="Sélectionner un dossier", parent=root)
        root.destroy()
        self._send_json({"path": os.path.normpath(folder) if folder else ""})

    def _handle_test_voice(self):
        body = self._read_json_body()
        engine = normalize_engine(body.get("tts_engine", "onecore"))
        voice_id = body.get("voice_id")
        lang = body.get("lang", "fr-FR")

        preferred = lang[:2] if lang else "fr"
        resolved = resolve_voice_with_fallbacks(
            engine=engine,
            desired_voice_id=voice_id,
            preferred_lang_base=preferred,
        )
        if resolved:
            voice_id = resolved["id"] if isinstance(resolved, dict) else resolved

        sample_text = "Bonjour, ceci est un test de synthèse vocale pour vérifier la voix."
        if str(lang).lower().startswith("en"):
            sample_text = "Hello, this is a speech synthesis test to check the voice."
        elif str(lang).lower().startswith("es"):
            sample_text = "Hola, esta es una prueba de síntesis de voz."
        elif str(lang).lower().startswith("de"):
            sample_text = "Hallo, dies ist ein Sprachsynthesetest."

        opts = DubOptions(
            tts_engine=engine,
            voice_id=voice_id,
            min_rate_tts=float(body.get("min_rate_tts", 1.2)),
            max_rate_tts=float(body.get("max_rate_tts", 1.8)),
        )

        def _play_sample():
            try:
                GLOBAL_STATE.broadcast("log", f"Génération de l'échantillon ({engine}, voix: {voice_id or 'défaut'})...")
                if engine == "onecore":
                    from add_dub.core.tts import synthesize_tts_for_subtitle
                    res = synthesize_tts_for_subtitle(sample_text, 3000, voice_id, opts)
                elif engine == "edge":
                    from add_dub.core.tts_edge import synthesize_tts_for_subtitle
                    res = synthesize_tts_for_subtitle(sample_text, 3000, voice_id, opts)
                elif engine == "gtts":
                    from add_dub.core.tts_gtts import synthesize_tts_for_subtitle
                    res = synthesize_tts_for_subtitle(sample_text, 3000, voice_id, opts)
                else:
                    return

                seg = res[0] if isinstance(res, tuple) else res
                out_sample = os.path.join(io_fs.TMP_DIR, "test_voice_preview.wav")
                seg.export(out_sample, format="wav")

                import winsound
                winsound.PlaySound(out_sample, winsound.SND_FILENAME | winsound.SND_ASYNC)
                GLOBAL_STATE.broadcast("log", "Échantillon audio joué avec succès.")
            except Exception as e:
                GLOBAL_STATE.broadcast("error", f"Erreur lors du test vocal : {e}")

        threading.Thread(target=_play_sample, daemon=True).start()
        self._send_json({"status": "ok"})

    def _handle_run(self):
        if GLOBAL_STATE.is_running:
            self._send_json({"error": "Un traitement est déjà en cours."}, status=400)
            return

        body = self._read_json_body()
        in_path = str(body.get("input_path", "")).strip()
        out_dir = str(body.get("output_dir", "")).strip() or io_fs.OUTPUT_DIR
        recursive = bool(body.get("recursive", False))
        preserve_tree = bool(body.get("preserve_tree", False))
        overwrite = bool(body.get("overwrite", False))
        skip_existing = False if overwrite else bool(body.get("skip_existing", True))

        limit_duration = bool(body.get("limit_duration", False))
        limit_duration_sec = int(body.get("limit_duration_sec", 60)) if limit_duration else None

        if not os.path.exists(in_path):
            self._send_json({"error": f"Chemin introuvable : {in_path}"}, status=400)
            return

        os.makedirs(out_dir, exist_ok=True)
        io_fs.set_base_dirs(
            input_dir=in_path if os.path.isdir(in_path) else os.path.dirname(in_path),
            output_dir=out_dir
        )

        engine = normalize_engine(body.get("tts_engine", "onecore"))
        voice_id = body.get("voice_id")
        preferred_lang = body.get("voice_lang", "fr-FR")
        resolved = resolve_voice_with_fallbacks(
            engine=engine,
            desired_voice_id=voice_id,
            preferred_lang_base=preferred_lang[:2] if preferred_lang else None,
        )
        if resolved:
            voice_id = resolved["id"] if isinstance(resolved, dict) else resolved

        raw_aud = str(body.get("audio_index", "auto")).strip().lower()
        aud_idx = None if raw_aud in ("auto", "none", "") else int(raw_aud)

        sub_mode = str(body.get("sub_mode", "auto")).lower()
        sub_idx = int(body.get("sub_index", 0))
        sub_choice = ("mkv", sub_idx) if sub_mode == "mkv" else None

        codec = str(body.get("audio_codec", "ac3")).lower()
        raw_bitrate = str(body.get("audio_bitrate", "256")).replace("k", "").strip()
        try:
            bitrate_int = int(raw_bitrate)
        except Exception:
            bitrate_int = 256

        audio_args = final_audio_codec_args(codec, bitrate_int)
        sub_codec = subtitle_codec_for_container(".mkv")

        tr_to = str(body.get("translate_to", "fr")).strip().lower()[:2] or "fr"
        tr_from_raw = str(body.get("translate_from", "auto")).strip().lower()
        tr_from = None if tr_from_raw in ("auto", "none", "") else tr_from_raw[:2]

        opts = DubOptions(
            audio_ffmpeg_index=aud_idx,
            sub_choice=sub_choice,
            orig_audio_lang=str(body.get("orig_audio_lang", "Original")).strip() or "Original",
            db_reduct=float(body.get("ducking_db", -5.0)),
            offset_ms=int(body.get("offset_ms", 0)),
            bg_mix=float(body.get("bg_mix", 1.0)),
            tts_mix=float(body.get("tts_mix", 1.0)),
            min_rate_tts=float(body.get("min_rate_tts", 1.2)),
            max_rate_tts=float(body.get("max_rate_tts", 1.8)),
            audio_codec=codec,
            audio_bitrate=bitrate_int,
            tts_engine=engine,
            voice_id=voice_id,
            audio_codec_args=audio_args,
            sub_codec=sub_codec,
            offset_video_ms=int(body.get("offset_video_ms", 0)),
            ask_test_before_cleanup=False,
            translate=bool(body.get("translate", False)),
            translate_to=tr_to,
            translate_from=tr_from,
            batch_mode=True,
            overwrite=overwrite,
            skip_existing=skip_existing,
            reuse_translated_subs=bool(body.get("reuse_translated_subs", True)),
            ask_reuse_subs=False,
        )

        ui_adapter = ServerUIAdapter(GLOBAL_STATE)
        svcs = self._build_services(ui_adapter, sub_mode, sub_idx)

        GLOBAL_STATE.is_running = True
        GLOBAL_STATE.broadcast("started", True)
        GLOBAL_STATE.broadcast("log", "=== Démarrage du traitement ===")

        GLOBAL_STATE.worker_thread = threading.Thread(
            target=self._run_worker,
            args=(in_path, out_dir, recursive, preserve_tree, limit_duration_sec, opts, svcs),
            daemon=True
        )
        GLOBAL_STATE.worker_thread.start()

        self._send_json({"status": "started"})

    def _build_services(self, ui: ServerUIAdapter, sub_src: str, sub_idx: int) -> Services:
        from add_dub.core.subtitles import (
            resolve_srt_for_video,
            find_sidecar_srt,
            _srt_in_srt_dir_for_video,
        )
        from add_dub.adapters.ffmpeg import get_track_info

        def _choose_files(files: list[str]) -> list[str]:
            return files

        def _choose_audio_track(input_video_path: str) -> int:
            tracks = get_track_info(input_video_path) or []
            if not tracks:
                return 0
            try:
                return int(tracks[0].get("index", 0))
            except Exception:
                return 0

        def _auto_sub_choice(input_video_path: str) -> tuple[str, Optional[int]]:
            try:
                if find_sidecar_srt(input_video_path):
                    return ("srt", None)
            except Exception:
                pass
            return ("mkv", 0)

        def _choose_subtitle_source(input_video_path: str):
            mode = (sub_src or "auto").lower()
            if mode == "srt":
                in_srt = _srt_in_srt_dir_for_video(input_video_path)
                if in_srt:
                    return ("srt", in_srt)
                sidecar = find_sidecar_srt(input_video_path)
                if sidecar:
                    return ("srt", sidecar)
                return ("srt", None)
            if mode == "mkv":
                return ("mkv", sub_idx)
            return _auto_sub_choice(input_video_path)

        return Services(
            resolve_srt_for_video=resolve_srt_for_video,
            generate_dub_audio=generate_dub_audio,
            choose_files=_choose_files,
            choose_audio_track=_choose_audio_track,
            choose_subtitle_source=_choose_subtitle_source,
            ui=ui,
        )

    def _run_worker(
        self,
        in_path: str,
        out_dir: str,
        recursive: bool,
        preserve_tree: bool,
        limit_duration_sec: Optional[int],
        base_opts: DubOptions,
        svcs: Services,
    ):
        try:
            targets: List[Tuple[str, str]] = []
            exts = (".mkv", ".mp4", ".avi", ".mov")

            if os.path.isfile(in_path):
                targets.append((in_path, ""))
            elif os.path.isdir(in_path):
                if recursive:
                    for root_dir, _, files in os.walk(in_path):
                        for f in files:
                            if f.lower().endswith(exts):
                                full = os.path.join(root_dir, f)
                                rel = os.path.relpath(root_dir, in_path)
                                targets.append((full, "" if rel == "." else rel))
                else:
                    for f in os.listdir(in_path):
                        full = os.path.join(in_path, f)
                        if os.path.isfile(full) and f.lower().endswith(exts):
                            targets.append((full, ""))

            total = len(targets)
            if total == 0:
                GLOBAL_STATE.broadcast("error", "Aucun fichier vidéo (.mkv, .mp4, .avi) trouvé dans le dossier spécifié.")
                return

            GLOBAL_STATE.broadcast("log", f"{total} vidéo(s) identifiée(s) à traiter.")

            for idx, (vid_path, rel_dir) in enumerate(targets, 1):
                if not GLOBAL_STATE.is_running:
                    GLOBAL_STATE.broadcast("log", "Traitement interrompu par l'utilisateur.")
                    break

                if preserve_tree and rel_dir:
                    target_out_dir = os.path.join(out_dir, rel_dir)
                else:
                    target_out_dir = out_dir

                os.makedirs(target_out_dir, exist_ok=True)
                GLOBAL_STATE.broadcast("log", f"\n--- [{idx}/{total}] : {os.path.basename(vid_path)} ---")

                aud_idx = base_opts.audio_ffmpeg_index
                if aud_idx is None:
                    aud_idx = svcs.choose_audio_track(vid_path)

                sub_ch = base_opts.sub_choice
                if sub_ch is None:
                    sub_ch = svcs.choose_subtitle_source(vid_path)

                run_opts = replace(base_opts, audio_ffmpeg_index=aud_idx, sub_choice=sub_ch)

                out = process_one_video(
                    input_video_path=vid_path,
                    input_video_name=os.path.basename(vid_path),
                    output_dir_path=target_out_dir,
                    opts=run_opts,
                    svcs=svcs,
                    limit_duration_sec=limit_duration_sec,
                )

                if out:
                    GLOBAL_STATE.broadcast("log", f"-> Succès : {out}")
                else:
                    GLOBAL_STATE.broadcast("error", f"-> Échec du doublage pour : {os.path.basename(vid_path)}")

                GLOBAL_STATE.broadcast("progress", int(idx * 100 / total))

            if GLOBAL_STATE.is_running:
                GLOBAL_STATE.broadcast("progress", 100.0)
                GLOBAL_STATE.broadcast("log", "\n=== Tous les traitements sont terminés avec succès ! ===")

        except Exception as e:
            GLOBAL_STATE.broadcast("error", f"Une exception inattendue est survenue : {e}")

        finally:
            GLOBAL_STATE.is_running = False
            GLOBAL_STATE.broadcast("finished", True)

    def _handle_stop(self):
        GLOBAL_STATE.is_running = False
        GLOBAL_STATE.broadcast("log", "Arrêt demandé...")
        self._send_json({"status": "stopping"})

    def _handle_sse_events(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        q = GLOBAL_STATE.add_event_listener()
        try:
            # Message initial de connexion
            self.wfile.write(b"data: {\"type\": \"connected\"}\n\n")
            self.wfile.flush()

            while True:
                try:
                    msg = q.get(timeout=20.0)
                    self.wfile.write(f"data: {msg}\n\n".encode("utf-8"))
                    self.wfile.flush()
                except queue.Empty:
                    # Keep-alive heartbeat
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
        except (ConnectionResetError, BrokenPipeError, Exception):
            pass
        finally:
            GLOBAL_STATE.remove_event_listener(q)


def start_server(port: int = 0) -> Tuple[ThreadedHTTPServer, int]:
    server = ThreadedHTTPServer(("127.0.0.1", port), ApiRequestHandler)
    actual_port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, actual_port
