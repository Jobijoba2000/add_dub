# add_dub/core/ducking.py
import os
from pydub import AudioSegment
from concurrent.futures import ThreadPoolExecutor
from add_dub.logger import (log_call, log_time)

try:
    import numpy as np  # optionnel : si indisponible, on bascule en mode pydub pur
except Exception:
    np = None


def _pcm_to_numpy(audio: AudioSegment):
    """
    Convertit un AudioSegment en tableau float32 [-1..1] + méta (fr, ch, sw, scale, dtype).
    Retourne (None, ...) si conversion numpy indisponible.
    """
    if np is None:
        return None, audio.frame_rate, audio.channels, audio.sample_width, None, None

    sw = audio.sample_width
    ch = audio.channels
    fr = audio.frame_rate
    raw = audio.raw_data
    frame_size = ch * sw

    if len(raw) % frame_size != 0:
        return None, fr, ch, sw, None, None

    n_frames = len(raw) // frame_size

    if sw == 2:
        arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
        arr = arr.reshape(n_frames, ch)
        arr /= 32768.0
        return arr, fr, ch, sw, 32768.0, np.int16

    elif sw == 4:
        arr = np.frombuffer(raw, dtype=np.int32).astype(np.float32)
        arr = arr.reshape(n_frames, ch)
        arr /= 2147483648.0
        return arr, fr, ch, sw, 2147483648.0, np.int32

    elif sw == 1:
        arr = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
        arr = arr.reshape(n_frames, ch)
        arr = (arr - 128.0) / 128.0
        return arr, fr, ch, sw, 128.0, np.uint8

    else:
        return None, fr, ch, sw, None, None


def _numpy_to_pcm(arr_f32, fr, ch, sw, scale, dtype):
    """
    Reconvertit un tableau float32 [-1..1] en PCM bytes selon (sw, scale, dtype).
    """
    arr = np.clip(arr_f32, -1.0, 1.0)

    if sw in (2, 4):
        out = (arr * scale).astype(dtype).reshape(-1)
        return out.tobytes(), sw

    elif sw == 1:
        out = (arr * scale + 128.0).round().astype(dtype).reshape(-1)
        return out.tobytes(), sw

    else:
        raise ValueError("sample_width non géré")


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
def lower_audio_during_subtitles(
    audio_file,
    subtitles,
    output_wav,
    reduction_db=-5.0,
    fade_duration=100,
    offset_ms=0,
):
    """
    Abaisse le niveau du BG pendant les sous-titres :
      - Hors dialogues : volume inchangé.
      - Pendant dialogues : réduction de 'reduction_db' (négatif) avec fondus d'entrée/sortie.

    Deux chemins :
      - Sans NumPy : montage segment-par-segment via pydub (plus lent).
      - Avec NumPy : enveloppe temporelle (plus rapide, garde le niveau global inchangé).
    """
    audio = AudioSegment.from_file(audio_file)
    subtitles = sorted(list(subtitles), key=lambda x: x[0])

    # Toujours interpréter la réduction comme une atténuation (valeur négative)
    reduction_db = -abs(reduction_db)

    env = _pcm_to_numpy(audio)
    if env[0] is None:
        # Chemin SANS NumPy : on reconstruit audio en remplaçant uniquement les zones dialoguées
        output = AudioSegment.empty()
        current_ms = 0

        # Fusion minimale des intervalles proches pour éviter des fades qui se chevauchent
        fused = _merge_close_intervals(subtitles, offset_ms, fade_duration)

        for start_ms, end_ms in fused:
            if start_ms > current_ms:
                output += audio[current_ms:start_ms]

            original_seg = audio[start_ms:end_ms]
            seg_duration = len(original_seg)

            if seg_duration > 2 * fade_duration:
                reduced_seg = original_seg.apply_gain(reduction_db)
                initial_transition = original_seg[:fade_duration].fade_out(fade_duration).overlay(
                    reduced_seg[:fade_duration].fade_in(fade_duration)
                )
                final_transition = reduced_seg[-fade_duration:].fade_out(fade_duration).overlay(
                    original_seg[-fade_duration:].fade_in(fade_duration)
                )
                middle = reduced_seg[fade_duration:seg_duration - fade_duration]
                new_seg = initial_transition + middle + final_transition
            else:
                new_seg = original_seg.apply_gain(reduction_db)

            output += new_seg
            current_ms = end_ms

        if current_ms < len(audio):
            output += audio[current_ms:]

        output.export(output_wav, format="wav")
        return output_wav

    # Chemin AVEC NumPy : enveloppe multiplicative sans cumul (min au lieu de *=)
    samples_f32, fr, ch, sw, scale, dtype = env
    n_frames = samples_f32.shape[0]
    envelope = np.ones(n_frames, dtype=np.float32)

    # Gain cible pendant dialogues (valeur < 1.0)
    gain = 10.0 ** (reduction_db / 20.0)

    fade_frames = max(0, int(round(fade_duration * fr / 1000.0)))

    # Intervalles fusionnés (en ms) pour éviter les recouvrements de rampes
    fused = _merge_close_intervals(subtitles, offset_ms, fade_duration)

    # Construction de l'enveloppe par "minimum" (pas de cumul d'atténuations)
    if fade_frames > 0:
        ramp_down = np.linspace(1.0, gain, fade_frames, dtype=np.float32)
        ramp_up = np.linspace(gain, 1.0, fade_frames, dtype=np.float32)

    for start_ms, end_ms in fused:
        s = int(round(start_ms * fr / 1000.0))
        e = int(round(end_ms * fr / 1000.0))
        s = max(0, min(n_frames, s))
        e = max(0, min(n_frames, e))
        if e <= s:
            continue

        seg_len = e - s
        if seg_len > 2 * fade_frames and fade_frames > 0:
            # Descente
            e0 = s + fade_frames
            if e0 > n_frames:
                e0 = n_frames
            # montée
            s2 = e - fade_frames
            if s2 < 0:
                s2 = 0
            # plateau
            mid_start = e0
            mid_end = s2

            # min() pour empêcher la baisse globale
            envelope[s:e0] = np.minimum(envelope[s:e0], ramp_down[: e0 - s])
            if mid_end > mid_start:
                envelope[mid_start:mid_end] = np.minimum(envelope[mid_start:mid_end], gain)
            envelope[s2:e] = np.minimum(envelope[s2:e], ramp_up[: e - s2])

        else:
            # Court segment : tout à gain
            envelope[s:e] = np.minimum(envelope[s:e], gain)

    # Application de l'enveloppe en blocs (threads) – hors dialogues = 1.0 (inchangé)
    max_workers = min((os.cpu_count() or 4), 8)
    blocks = max_workers * 4
    block_size = (n_frames + blocks - 1) // blocks

    def _apply_block(b):
        i0 = b * block_size
        i1 = min(n_frames, i0 + block_size)
        if i0 < i1:
            samples_f32[i0:i1, :] *= envelope[i0:i1, None]

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        ex.map(_apply_block, range(blocks))

    # Export
    raw_bytes, out_sw = _numpy_to_pcm(samples_f32, fr, ch, sw, scale, dtype)
    out_seg = AudioSegment(data=raw_bytes, sample_width=out_sw, frame_rate=fr, channels=ch)
    out_seg.export(output_wav, format="wav")
    return output_wav
