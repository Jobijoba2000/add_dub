# add_dub/core/tts_generate.py
import os
import math
from multiprocessing import cpu_count
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, wait, FIRST_COMPLETED
from typing import List, Tuple, Optional
from pprint import pprint
import numpy as np
from pydub import AudioSegment

from add_dub.core.options import DubOptions
from add_dub.core.subtitles import parse_srt_file
from add_dub.workers import tts_worker
from add_dub.logger import (log_call, log_time)
from add_dub.core.tts_registry import normalize_engine


def _coerce_gtts_lang(voice_or_lang: str) -> str:
    """
    Convertit une voix OneCore/Edge en code langue court 'fr', 'en', etc. pour gTTS.
    """
    v = str(voice_or_lang or "").strip()
    if not v:
        return "en"
    if "HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Speech_OneCore\\Voices\\Tokens\\" in v:
        import re
        m = re.search(r"_([a-z]{2})[A-Z]{2}_", v)
        if m:
            return m.group(1).lower()
        return "en"
    if "-" in v and len(v.split("-")[0]) == 2:
        return v.split("-")[0].lower()
    if len(v) == 2:
        return v.lower()
    return "en"


def _load_segment_as_array(
    path: str,
    target_sr: int,
    target_ch: int,
    target_sw: int,
    trim_lead_ms: int,
    target_ms: int,
) -> np.ndarray:
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
    dtype = np.int16 if target_sw == 2 else (np.int8 if target_sw == 1 else np.int32)
    arr = np.frombuffer(raw, dtype=dtype)
    arr = arr.reshape(-1, target_ch)

    if dtype == np.int8:
        arr = (arr.astype(np.int16) << 8)
    elif dtype == np.int32:
        arr = (arr >> 16).astype(np.int16)

    return arr


def _export_int16_wav(array_int16: np.ndarray, sr: int, ch: int, out_path: str) -> None:
    seg = AudioSegment(
        array_int16.tobytes(),
        frame_rate=sr,
        sample_width=2,
        channels=ch,
    )
    seg.export(out_path, format="wav")


@log_time
@log_call()
def generate_dub_audio(
    srt_file: str,
    output_wav: str,
    opts: DubOptions,
    *,
    duration_limit_sec: Optional[int] = None,
    target_total_duration_ms: Optional[int] = None,
) -> str:
    """
    Génère la piste TTS alignée sur le SRT et retourne le chemin du WAV généré.
    """
    subtitles = parse_srt_file(srt_file, duration_limit_sec=duration_limit_sec)
    if not subtitles:
        AudioSegment.silent(duration=0).export(output_wav, format="wav")
        return output_wav

    # Ajustement gTTS si nécessaire
    if normalize_engine(opts.tts_engine) == "gtts":
        opts.voice_id = _coerce_gtts_lang(opts.voice_id or "fr")

    jobs: List[Tuple[int, int, int, str, str, DubOptions]] = []
    for idx, (start, end, text) in enumerate(subtitles):
        jobs.append((idx, int(start * 1000), int(end * 1000), text, opts.voice_id, opts))

    max_workers = min(20, max(1, cpu_count()))
    results: List[Optional[Tuple[str, int, int]]] = [None] * len(jobs)

    total = len(jobs)
    done = 0
    print(f"\rTTS: 0% [0/{total}]", end="", flush=True)

    FREEZE_TIMEOUT = 5

    ex = ProcessPoolExecutor(max_workers=max_workers)
    try:
        fut_to_job = {ex.submit(tts_worker, j): j for j in jobs}
        pending = set(fut_to_job.keys())

        while pending:
            done_set, pending = wait(pending, timeout=FREEZE_TIMEOUT, return_when=FIRST_COMPLETED)

            if not done_set:
                print("\n[WARN] Aucune avancée TTS. Relance synchrone des segments restants...")
                for fut in list(pending):
                    job = fut_to_job[fut]
                    try:
                        fut.cancel()
                    except Exception:
                        pass
                    idx, path, s_ms, e_ms = tts_worker(job)
                    results[idx] = (path, s_ms, e_ms)
                    done += 1
                    pct = int(done * 100 / total)
                    print(f"\rTTS: {pct}% [{done}/{total}]", end="", flush=True)
                pending.clear()
                break

            for fut in done_set:
                job = fut_to_job[fut]
                try:
                    idx, path, s_ms, e_ms = fut.result()
                except Exception:
                    idx, path, s_ms, e_ms = tts_worker(job)
                results[idx] = (path, s_ms, e_ms)
                done += 1
                pct = int(done * 100 / total)
                print(f"\rTTS: {pct}% [{done}/{total}]", end="", flush=True)

    finally:
        ex.shutdown(wait=False, cancel_futures=True)

    first_path, _, _ = results[0]  # type: ignore
    first_seg = AudioSegment.from_file(first_path)
    target_sr = first_seg.frame_rate
    target_ch = first_seg.channels
    target_sw = first_seg.sample_width
    if target_sw not in (1, 2, 4):
        target_sw = 2

    max_end_ms = 0
    for (start, end, _text), _res in zip(subtitles, results):
        s = int(start * 1000) + (opts.offset_ms or 0)
        e = int(end * 1000) + (opts.offset_ms or 0)
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

    samples_total = int(math.ceil(final_ms * target_sr / 1000.0)) + 1
    if samples_total <= 1:
        AudioSegment.silent(duration=0).export(output_wav, format="wav")
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

    tasks = []
    for (start, end, _text), res in zip(subtitles, results):
        path, _s_ms, _e_ms = res  # type: ignore
        start_ms = int(start * 1000) + (opts.offset_ms or 0)
        end_ms = int(end * 1000) + (opts.offset_ms or 0)

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

        if i0 >= samples_total:
            return
        if i1 > samples_total:
            arr = arr[: samples_total - i0]
            i1 = samples_total

        if arr.size > 0:
            final_buf[i0:i1, :] = arr

    max_threads = min(32, max(1, cpu_count() * 2))
    with ThreadPoolExecutor(max_workers=max_threads) as pool:
        list(pool.map(_worker_load_and_place, tasks))

    for res in results:
        if not res:
            continue
        path, _, _ = res
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except Exception:
            pass

    _export_int16_wav(final_buf, target_sr, target_ch, output_wav)

    print()
    return output_wav
