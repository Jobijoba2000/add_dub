# src/add_dub/core/tts_generate.py
import os
import time
from multiprocessing import cpu_count
from concurrent.futures import ProcessPoolExecutor, as_completed, ThreadPoolExecutor
from typing import List, Tuple, Optional

import numpy as np
from pydub import AudioSegment

from add_dub.core.subtitles import parse_srt_file
from add_dub.workers import tts_worker


def _load_segment_as_array(
    path: str,
    target_sr: int,
    target_ch: int,
    target_sw: int,
    trim_lead_ms: int,
    target_ms: int,
) -> np.ndarray:
    """
    Charge un segment depuis 'path', convertit au format cible (sr, ch, sw),
    applique une coupe initiale (trim_lead_ms), puis ajuste strictement à target_ms
    (coupe si trop long, complète avec silence si trop court). Retourne un np.ndarray int16 shape (n, ch).
    """
    seg = AudioSegment.from_file(path)
    if seg.frame_rate != target_sr:
        seg = seg.set_frame_rate(target_sr)
    if seg.channels != target_ch:
        seg = seg.set_channels(target_ch)
    if seg.sample_width != target_sw:
        seg = seg.set_sample_width(target_sw)

    if trim_lead_ms > 0:
        seg = seg[trim_lead_ms:] if trim_lead_ms < len(seg) else AudioSegment.silent(duration=0, frame_rate=target_sr)

    if len(seg) > target_ms:
        seg = seg[:target_ms]
    elif len(seg) < target_ms:
        seg = seg + AudioSegment.silent(duration=(target_ms - len(seg)), frame_rate=target_sr)

    raw = seg.raw_data
    dtype = np.int16 if target_sw == 2 else np.int8 if target_sw == 1 else np.int32
    arr = np.frombuffer(raw, dtype=dtype)

    if target_ch == 2:
        arr = arr.reshape(-1, 2)
    else:
        arr = arr.reshape(-1, 1)

    # On retourne toujours int16 (pcm_s16)
    if dtype != np.int16:
        # Normalisation simple vers int16
        if dtype == np.int8:
            arr = (arr.astype(np.int16) << 8)
        elif dtype == np.int32:
            arr = (arr >> 16).astype(np.int16)

    return arr


def _export_int16_wav(array_int16: np.ndarray, sr: int, ch: int, out_path: str) -> None:
    """
    Exporte un tampon int16 (shape = [n, ch]) en WAV PCM s16le à l'emplacement 'out_path'.
    """
    seg = AudioSegment(
        array_int16.tobytes(),
        frame_rate=sr,
        sample_width=2,
        channels=ch,
    )
    seg.export(out_path, format="wav")


def generate_dub_audio(
    srt_file: str,
    output_wav: str,
    voice_id: str,
    *,
    duration_limit_sec: Optional[int] = None,
    target_total_duration_ms: Optional[int] = None,
    offset_ms: int = 0,
) -> str:
    """
    Génère la piste TTS alignée sur le SRT.
    Retourne le chemin du WAV généré (output_wav).
    """
    subtitles = parse_srt_file(srt_file, duration_limit_sec=duration_limit_sec)
    if not subtitles:
        AudioSegment.silent(duration=0).export(output_wav, format="wav")
        return output_wav

    jobs: List[Tuple[int, int, int, str, str]] = []
    for idx, (start, end, text) in enumerate(subtitles):
        jobs.append((idx, int(start * 1000), int(end * 1000), text, voice_id))

    max_workers = min(20, max(1, cpu_count()))
    results: List[Optional[Tuple[str, int, int]]] = [None] * len(jobs)

    total = len(jobs)
    done = 0
    print(f"\rTTS: 0% [0/{total}]", end="", flush=True)
    t0_tts = time.perf_counter()

    # Synthèse TTS en parallèle (processus)
    with ProcessPoolExecutor(max_workers=max_workers) as ex:
        fut_to_idx = {ex.submit(tts_worker, j): j[0] for j in jobs}
        for fut in as_completed(fut_to_idx):
            idx, path, s_ms, e_ms = fut.result()
            results[idx] = (path, s_ms, e_ms)
            done += 1
            pct = int(done * 100 / total)
            print(f"\rTTS: {pct}% [{done}/{total}]", end="", flush=True)

    print(f"\n{time.perf_counter() - t0_tts:.3f}")

    print("\rExport en cours...")
    t0_export = time.perf_counter()

    # Paramètres cible audio (on prend ceux du premier segment)
    # On lit UN segment pour récupérer sr/ch/sw, puis on repartira en parallèle
    first_path, _, _ = results[0]
    first_seg = AudioSegment.from_file(first_path)
    target_sr = first_seg.frame_rate
    target_ch = first_seg.channels
    target_sw = first_seg.sample_width  # bytes
    # On force en s16 à l'export pour rester cohérent
    if target_sw not in (1, 2, 4):
        target_sw = 2

    # Calcul de la durée totale nécessaire
    max_end_ms = 0
    for (start, end, _text), res in zip(subtitles, results):
        start_ms = int(start * 1000) + offset_ms
        end_ms = int(end * 1000) + offset_ms

        if end_ms <= 0:
            continue
        if start_ms < 0:
            start_ms = 0
        if end_ms <= start_ms:
            continue
        if end_ms > max_end_ms:
            max_end_ms = end_ms

    final_ms = target_total_duration_ms if (target_total_duration_ms is not None) else max_end_ms
    if final_ms is None or final_ms < 0:
        final_ms = 0

    # Pré-allocation du tampon final int16
    samples_total = int((final_ms / 1000.0) * target_sr)
    if samples_total <= 0:
        AudioSegment.silent(duration=0).export(output_wav, format="wav")
        # Nettoyage des segments
        for res in results:
            if res:
                path, _, _ = res
                try:
                    if path and os.path.exists(path):
                        os.remove(path)
                except Exception:
                    pass
        return output_wav

    # Shape [n, ch], int16, initialisé à 0 (silence)
    final_buf = np.zeros((samples_total, target_ch), dtype=np.int16)

    # Préparation des tâches de chargement/décodage (I/O bound → threads)
    tasks = []
    for (start, end, _text), res in zip(subtitles, results):
        path, s_ms, e_ms = res  # type: ignore
        start_ms = int(start * 1000) + offset_ms
        end_ms = int(end * 1000) + offset_ms

        if end_ms <= 0:
            continue
        trim_lead = 0
        if start_ms < 0:
            trim_lead = -start_ms
            start_ms = 0
        if end_ms <= start_ms:
            continue

        target_ms = end_ms - start_ms
        tasks.append((path, start_ms, target_ms, trim_lead))

    # Chargement parallèle des segments, placement dans le tampon
    def _worker_load_and_place(args):
        path, start_ms, target_ms, trim_lead = args
        arr = _load_segment_as_array(
            path=path,
            target_sr=target_sr,
            target_ch=target_ch,
            target_sw=target_sw,
            trim_lead_ms=trim_lead,
            target_ms=target_ms,
        )
        i0 = int((start_ms / 1000.0) * target_sr)
        i1 = i0 + arr.shape[0]
        # Copie (ou addition si on veut tolérer un éventuel recouvrement)
        # Ici, on copie (SRT typiques non recouvrants)
        final_buf[i0:i1, :] = arr

    max_threads = min(32, max(1, cpu_count() * 2))
    with ThreadPoolExecutor(max_workers=max_threads) as pool:
        list(pool.map(_worker_load_and_place, tasks))

    # Nettoyage des fichiers temporaires
    for res in results:
        if not res:
            continue
        path, _, _ = res
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except Exception:
            pass

    # Export final en WAV pcm_s16le
    _export_int16_wav(final_buf, target_sr, target_ch, output_wav)

    t_export = time.perf_counter() - t0_export
    print(f"{t_export:.3f}")
    print("\rExport terminé")

    return output_wav
