# src/add_dub/core/ducking.py
import os
from pydub import AudioSegment
from concurrent.futures import ThreadPoolExecutor

try:
    import numpy as np  # optionnel : si indisponible, on bascule en mode pydub pur
except Exception:
    np = None


def _pcm_to_numpy(audio: AudioSegment):
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
    arr = np.clip(arr_f32, -1.0, 1.0)
    if sw in (2, 4):
        out = (arr * scale).astype(dtype).reshape(-1)
        return out.tobytes(), sw
    elif sw == 1:
        out = (arr * scale + 128.0).round().astype(dtype).reshape(-1)
        return out.tobytes(), sw
    else:
        raise ValueError("sample_width non géré")


def lower_audio_during_subtitles(
    audio_file,
    subtitles,
    output_wav,
    reduction_db=-5.0,
    fade_duration=100,
    offset_ms=0,
):
    audio = AudioSegment.from_file(audio_file)
    subtitles = sorted(list(subtitles), key=lambda x: x[0])

    env = _pcm_to_numpy(audio)
    if env[0] is None:
        # Chemin sans numpy : montage pydub
        output = AudioSegment.empty()
        current_ms = 0
        for start, end, _ in subtitles:
            start_ms = int(start * 1000 + offset_ms)
            end_ms = int(end * 1000 + offset_ms)
            if end_ms <= 0:
                continue
            if start_ms < 0:
                start_ms = 0
            if end_ms <= start_ms:
                continue
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

    # Chemin numpy : enveloppe multiplicative avec fondus
    samples_f32, fr, ch, sw, scale, dtype = env
    n_frames = samples_f32.shape[0]
    envelope = np.ones(n_frames, dtype=np.float32)
    gain = 10.0 ** (reduction_db / 20.0)
    fade_frames = max(0, int(round(fade_duration * fr / 1000.0)))
    offset_s = offset_ms / 1000.0

    for start, end, _ in subtitles:
        s = int(round((start + offset_s) * fr))
        e = int(round((end + offset_s) * fr))
        if e <= 0:
            continue
        s = max(0, s)
        e = min(n_frames, e)
        if e <= s:
            continue
        seg_len = e - s
        if seg_len > 2 * fade_frames:
            if fade_frames > 0:
                ramp_down = np.linspace(1.0, gain, fade_frames, dtype=np.float32)
                envelope[s:s + fade_frames] *= ramp_down
            mid_start = s + fade_frames
            mid_end = e - fade_frames
            if mid_end > mid_start:
                envelope[mid_start:mid_end] *= gain
            if fade_frames > 0:
                ramp_up = np.linspace(gain, 1.0, fade_frames, dtype=np.float32)
                envelope[e - fade_frames:e] *= ramp_up
        else:
            envelope[s:e] *= gain

    max_workers = min((os.cpu_count() or 4), 8) if np is not None else 4
    blocks = max_workers * 4
    block_size = (n_frames + blocks - 1) // blocks

    def _apply_block(b):
        i0 = b * block_size
        i1 = min(n_frames, i0 + block_size)
        if i0 < i1:
            samples_f32[i0:i1, :] *= envelope[i0:i1, None]

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        ex.map(_apply_block, range(blocks))

    raw_bytes, out_sw = _numpy_to_pcm(samples_f32, fr, ch, sw, scale, dtype)
    out_seg = AudioSegment(data=raw_bytes, sample_width=out_sw, frame_rate=fr, channels=ch)
    out_seg.export(output_wav, format="wav")
    return output_wav
