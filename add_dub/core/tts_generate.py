"""Synthèse isolée et assemblage déterministe, avec mémoire bornée."""
from dataclasses import replace
import multiprocessing
import os
from pathlib import Path
import tempfile
import wave
import numpy as np
from pydub import AudioSegment
from add_dub.core.subtitles import parse_srt_file
from add_dub.core.validation import validate_options
from add_dub.io import fs
from add_dub.workers import tts_worker

STALL_SECONDS = 240


def synthesize_jobs(jobs, ui=None):
    pool = multiprocessing.get_context('spawn').Pool(min(8, max(1, os.cpu_count() or 1)))
    results = []
    try:
        iterator = pool.imap_unordered(tts_worker, jobs, chunksize=1)
        for completed in range(len(jobs)):
            try:
                result = iterator.next(timeout=STALL_SECONDS)
            except multiprocessing.TimeoutError as exc:
                raise TimeoutError('La synthèse ne répond plus ; ses processus ont été interrompus.') from exc
            results.append(result)
            if ui:
                ui.progress(90 * (completed + 1) / len(jobs))
        pool.close()
        return sorted(results, key=lambda item: item[0])
    except BaseException:
        pool.terminate()
        raise
    finally:
        pool.join()


def assemble_segments(cues, results, output_wav, total_ms, offset_ms=0):
    """Somme des cues en int32 sur disque, saturation seulement à l'export."""
    with open(results[0][1], 'rb') as stream:
        first = AudioSegment.from_file(stream, format='wav')
    rate, channels = first.frame_rate, first.channels
    frames = max(1, round(total_ms * rate / 1000))
    fd, buffer_path = tempfile.mkstemp(suffix='.pcm', dir=fs.get_tmp_dir())
    os.close(fd)
    buffer = None
    try:
        with open(buffer_path, 'wb') as backing:
            backing.truncate(frames * channels * 4)
        buffer = np.memmap(buffer_path, mode='r+', dtype=np.int32, shape=(frames, channels))
        for (start, end, _), result in zip(cues, results):
            start_ms, end_ms = round(start * 1000) + offset_ms, round(end * 1000) + offset_ms
            if end_ms <= 0 or start_ms >= total_ms:
                continue
            with open(result[1], 'rb') as stream:
                segment = AudioSegment.from_file(stream, format='wav').set_frame_rate(rate).set_channels(channels).set_sample_width(2)
            segment = segment[max(0, -start_ms):max(0, end_ms - start_ms)]
            values = np.frombuffer(segment.raw_data, dtype=np.int16).reshape(-1, channels)
            begin = max(0, round(start_ms * rate / 1000))
            count = min(len(values), frames - begin)
            if count > 0:
                buffer[begin:begin + count] += values[:count].astype(np.int32)
        with wave.open(str(output_wav), 'wb') as output:
            output.setparams((channels, 2, rate, 0, 'NONE', 'not compressed'))
            for begin in range(0, frames, 65536):
                chunk = np.clip(buffer[begin:begin + 65536], -32768, 32767).astype('<i2')
                output.writeframesraw(chunk.tobytes())
    finally:
        if buffer is not None:
            buffer.flush()
            buffer._mmap.close()
        Path(buffer_path).unlink(missing_ok=True)


def generate_dub_audio(srt_file, output_wav, opts, *, duration_limit_sec=None,
                       target_total_duration_ms=None, ui=None):
    validate_options(opts)
    cues = parse_srt_file(srt_file, duration_limit_sec)
    if not cues:
        raise ValueError('Aucun sous-titre vocalisable.')
    with tempfile.TemporaryDirectory(prefix='tts-', dir=fs.get_tmp_dir()) as directory:
        opts = replace(opts, work_dir=directory)
        jobs = [(i, round(a * 1000), round(b * 1000), text, opts.voice_id, opts)
                for i, (a, b, text) in enumerate(cues)]
        results = synthesize_jobs(jobs, ui)
        if len(results) != len(cues) or [item[0] for item in results] != list(range(len(cues))):
            raise RuntimeError('Synthèse incomplète.')
        total_ms = target_total_duration_ms
        if total_ms is None:
            total_ms = max(round(end * 1000) + opts.offset_ms for _, end, _ in cues)
        assemble_segments(cues, results, output_wav, max(0, int(total_ms)), opts.offset_ms)
    if ui:
        ui.progress(100)
    return output_wav
