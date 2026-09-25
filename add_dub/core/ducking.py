"""Ducking PCM par blocs : mémoire indépendante de la durée du film."""
import wave
import numpy as np
from add_dub.logger import log_time, log_call

def _merge_close_intervals(subtitles, offset_ms, fade_ms, min_gap_ms=200):
    """
    Fusionne les intervalles de sous-titres trop proches pour éviter les recouvrements de fades.
    Entrée : list[(start_s, end_s, text)]
    Sortie : list[(start_ms, end_ms)] après offset, clamp à [0, +inf), fusion si gap < seuil.
    """
    # Conversion en ms + offset
    items = []
    for start_s, end_s, _ in subtitles:
        s = int(round(start_s * 1000)) + offset_ms
        e = int(round(end_s * 1000)) + offset_ms
        if e <= 0:
            continue
        if s < 0:
            s = 0
        if e <= s:
            continue
        items.append((s, e))

    if not items:
        return []

    # Tri + fusion si gap trop petit (seuil = max(fade_ms, min_gap_ms))
    items.sort()
    gap_thresh = max(int(fade_ms), int(min_gap_ms))

    merged = []
    cs, ce = items[0]
    for s, e in items[1:]:
        if s - ce < gap_thresh:
            # Fusion
            ce = max(ce, e)
        else:
            merged.append((cs, ce))
            cs, ce = s, e
    merged.append((cs, ce))
    return merged


@log_time
@log_call(exclude="subtitles")
def lower_audio_during_subtitles(audio_file, subtitles, output_wav, reduction_db=-5.0,
                                 fade_duration=100, offset_ms=0):
    gain = 10 ** (-abs(reduction_db) / 20)
    with wave.open(str(audio_file), 'rb') as source, wave.open(str(output_wav), 'wb') as target:
        channels, width, rate, frames, _, _ = source.getparams()
        if width not in (1, 2, 4):
            raise ValueError('Le ducking attend un WAV PCM 8, 16 ou 32 bits.')
        target.setparams(source.getparams())
        intervals = [(round(a * rate / 1000), round(b * rate / 1000))
                     for a,b in _merge_close_intervals(subtitles, offset_ms, fade_duration)]
        fade = max(0, round(fade_duration * rate / 1000))
        dtype = {1: np.dtype('u1'), 2: np.dtype('<i2'), 4: np.dtype('<i4')}[width]
        first = 0
        for begin in range(0, frames, 65536):
            raw = source.readframes(min(65536, frames - begin))
            data = np.frombuffer(raw, dtype=dtype).reshape(-1, channels)
            end = begin + len(data)
            envelope = np.ones(len(data), dtype=np.float64)
            while first < len(intervals) and intervals[first][1] <= begin:
                first += 1
            for a,b in intervals[first:]:
                if a >= end:
                    break
                left, right = max(a, begin), min(b, end)
                if right <= left:
                    continue
                positions = np.arange(left, right)
                values = np.full(right-left, gain)
                if fade > 0 and b-a > 2*fade:
                    values = np.interp(positions, [a, a+fade, b-fade, b-1], [1, gain, gain, 1])
                envelope[left-begin:right-begin] = np.minimum(envelope[left-begin:right-begin], values)
            if np.all(envelope == 1):
                target.writeframesraw(raw)
                continue
            centered = data.astype(np.float64) - (128 if width == 1 else 0)
            scaled = np.rint(centered * envelope[:, None]) + (128 if width == 1 else 0)
            limits = np.iinfo(dtype)
            target.writeframesraw(np.clip(scaled, limits.min, limits.max).astype(dtype).tobytes())
    return output_wav
