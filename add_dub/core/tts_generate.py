# add_dub/core/tts_generate.py
import os
import math
from multiprocessing import cpu_count
from concurrent.futures import ProcessPoolExecutor, as_completed, ThreadPoolExecutor
from typing import List, Tuple, Optional
import gc
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
    Charge un segment, le convertit au format cible, applique un trim éventuel,
    et l'ajuste exactement à target_ms (coupe ou silence). Retourne int16 (n, ch).
    """
    seg = AudioSegment.from_file(path)

    # Normalisation au format cible uniquement si nécessaire
    if seg.frame_rate != target_sr:
        seg = seg.set_frame_rate(target_sr)
    if seg.channels != target_ch:
        seg = seg.set_channels(target_ch)
    if seg.sample_width != target_sw:
        seg = seg.set_sample_width(target_sw)

    # Trim en tête si le sous-titre démarre avant zéro (offset négatif)
    if trim_lead_ms > 0:
        seg = seg[trim_lead_ms:] if trim_lead_ms < len(seg) else AudioSegment.silent(duration=0, frame_rate=target_sr)

    # Ajustement strict à la fenêtre
    if len(seg) > target_ms:
        seg = seg[:target_ms]
    elif len(seg) < target_ms:
        seg = seg + AudioSegment.silent(duration=(target_ms - len(seg)), frame_rate=target_sr)

    raw = seg.raw_data
    dtype = np.int16 if target_sw == 2 else (np.int8 if target_sw == 1 else np.int32)
    arr = np.frombuffer(raw, dtype=dtype).reshape(-1, target_ch)

    # Sortie toujours en int16
    if dtype == np.int8:
        arr = (arr.astype(np.int16) << 8)
    elif dtype == np.int32:
        arr = (arr >> 16).astype(np.int16)

    return arr


def _export_int16_wav(array_int16: np.ndarray, sr: int, ch: int, out_path: str) -> None:
    """
    Exporte un tampon int16 (n, ch) en WAV PCM s16.
    """
    seg = AudioSegment(
        array_int16.tobytes(),
        frame_rate=sr,
        sample_width=2,
        channels=ch,
    )
    seg.export(out_path, format="wav")


def _first_existing_path(results: List[Optional[Tuple[str, int, int]]]) -> Optional[str]:
    for res in results:
        if res:
            path, _, _ = res
            if path and os.path.exists(path):
                return path
    return None


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
    Génère la piste TTS alignée sur le SRT et retourne le chemin du WAV généré.
    """
    subtitles = parse_srt_file(srt_file, duration_limit_sec=duration_limit_sec)
    if not subtitles:
        AudioSegment.silent(duration=0).export(output_wav, format="wav")
        return output_wav

    # Préparation des jobs (un sous-titre => un segment TTS)
    jobs: List[Tuple[int, int, int, str, str]] = []
    for idx, (start, end, text) in enumerate(subtitles):
        jobs.append((idx, int(start * 1000), int(end * 1000), text, voice_id))

    max_workers = min(20, max(1, cpu_count()))
    results: List[Optional[Tuple[str, int, int]]] = [None] * len(jobs)

    total = len(jobs)
    done = 0
    print(f"\rTTS: 0% [0/{total}]", end="", flush=True)

    # Exécution TTS sans watchdog dangereux ni relance synchrone concurrente
    with ProcessPoolExecutor(max_workers=max_workers) as ex:
        fut_to_idx = {ex.submit(tts_worker, j): j[0] for j in jobs}
        for fut in as_completed(fut_to_idx):
            idx = fut_to_idx[fut]
            try:
                r_idx, path, s_ms, e_ms = fut.result()
            except Exception:
                # Rejoue ce job une fois en secours (dans le processus parent) ; échec rare
                r_idx, path, s_ms, e_ms = tts_worker(jobs[idx])
            results[r_idx] = (path, s_ms, e_ms)

            done += 1
            pct = int(done * 100 / total)
            print(f"\rTTS: {pct}% [{done}/{total}]", end="", flush=True)

    print()  # retour à la ligne après 100%

    # Déterminer le format cible depuis le premier segment existant
    first_path = _first_existing_path(results)
    if first_path is None:
        # Aucun segment valide : exporter un WAV vide
        AudioSegment.silent(duration=0).export(output_wav, format="wav")
        return output_wav

    first_seg = AudioSegment.from_file(first_path)
    target_sr = first_seg.frame_rate
    target_ch = first_seg.channels
    target_sw = first_seg.sample_width
    if target_sw not in (1, 2, 4):
        target_sw = 2  # sécurité

    # Calcul de la durée finale (ms)
    max_end_ms = 0
    for (start, end, _text), _res in zip(subtitles, results):
        s = int(start * 1000) + offset_ms
        e = int(end * 1000) + offset_ms
        if e <= 0:
            continue
        if s < 0:
            s = 0
        if e <= s:
            continue
        if e > max_end_ms:
            max_end_ms = e

    final_ms = target_total_duration_ms if (target_total_duration_ms is not None) else max_end_ms
    final_ms = max(0, int(final_ms))

    # Pré-allocation du tampon final (ajout d'1 frame de marge pour absorber les arrondis)
    samples_total = int(math.ceil(final_ms * target_sr / 1000.0)) + 1
    if samples_total <= 1:
        AudioSegment.silent(duration=0).export(output_wav, format="wav")
        # Nettoyage
        for res in results:
            if res:
                path, _, _ = res
                try:
                    if path and os.path.exists(path):
                        os.remove(path)
                except Exception:
                    pass
        return output_wav

    final_buf = np.zeros((samples_total, target_ch), dtype=np.int16)

    # Préparer les tâches de placement
    tasks = []
    for (start, end, _text), res in zip(subtitles, results):
        if not res:
            continue
        path, _s_ms, _e_ms = res
        if not path or not os.path.exists(path):
            continue

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

    # Chargement parallèle des segments et placement sécurisé
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

        # Garde-fous indices
        if i0 >= samples_total:
            return
        if i1 > samples_total:
            arr = arr[: samples_total - i0]
            i1 = samples_total

        if arr.size > 0:
            final_buf[i0:i1, :] = arr

    # Threads raisonnables (évite de surconcurrencer le disque)
    max_threads = max(1, cpu_count())
    with ThreadPoolExecutor(max_workers=max_threads) as pool:
        list(pool.map(_worker_load_and_place, tasks))

    # Nettoyage des petits WAV TTS
    for res in results:
        if not res:
            continue
        path, _, _ = res
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except Exception:
            pass

    # Export final
    _export_int16_wav(final_buf, target_sr, target_ch, output_wav)

    print("\rExport terminé")
    gc.collect()
    return output_wav
