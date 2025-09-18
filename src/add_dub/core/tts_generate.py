# src/add_dub/core/tts_generate.py
import os
import time
from multiprocessing import cpu_count
from concurrent.futures import ProcessPoolExecutor, as_completed
from pydub import AudioSegment

from add_dub.core.subtitles import parse_srt_file
from add_dub.workers import tts_worker


def generate_dub_audio(
    srt_file: str,
    output_wav: str,
    voice_id: str,
    *,
    duration_limit_sec: int | None = None,
    target_total_duration_ms: int | None = None,
    offset_ms: int = 0,  # <-- on ne dépend plus d'un global ; on passera la valeur depuis __main__ ensuite
) -> str:
    """
    Génère la piste TTS alignée sur le SRT.
    Retourne le chemin du WAV généré (output_wav).
    """
    subtitles = parse_srt_file(srt_file, duration_limit_sec=duration_limit_sec)
    if not subtitles:
        AudioSegment.silent(duration=0).export(output_wav, format="wav")
        return output_wav
    
    # Jobs TTS (un sous-titre => un segment)
    jobs = []
    for idx, (start, end, text) in enumerate(subtitles):
        jobs.append((idx, int(start * 1000), int(end * 1000), text, voice_id))

    max_workers = min(20, max(1, cpu_count()))
    results = [None] * len(jobs)

    total = len(jobs)
    done = 0
    print(f"\rTTS: 0% [0/{total}]", end="", flush=True)

    # Multiprocessing : on délègue à tts_worker (défini dans add_dub.workers)
    with ProcessPoolExecutor(max_workers=max_workers) as ex:
        fut_to_idx = {ex.submit(tts_worker, j): j[0] for j in jobs}
        for fut in as_completed(fut_to_idx):
            idx, path, s_ms, e_ms = fut.result()
            results[idx] = (path, s_ms, e_ms)

            done += 1
            pct = int(done * 100 / total)
            print(f"\rTTS: {pct}% [{done}/{total}]", end="", flush=True)

    print()  # retour à la ligne après 100%
    print("\rExport en cours...")
    
    # Recomposition de la piste TTS complète
    dub_audio = AudioSegment.empty()
    current_ms = 0
    try:
        for (start, end, _text), res in zip(subtitles, results):
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

            if start_ms > current_ms:
                dub_audio += AudioSegment.silent(duration=start_ms - current_ms)

            path, _, _ = res
            seg = AudioSegment.from_file(path)
            if trim_lead > 0:
                seg = seg[trim_lead:] if trim_lead < len(seg) else AudioSegment.silent(duration=0)

            target = end_ms - start_ms
            if len(seg) > target:
                seg = seg[:target]
            elif len(seg) < target:
                seg += AudioSegment.silent(duration=(target - len(seg)))

            dub_audio += seg
            current_ms = end_ms
    finally:
        # Nettoyage des segments temporaires
        for res in results:
            if not res:
                continue
            path, _, _ = res
            try:
                if path and os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass

    if target_total_duration_ms is not None and len(dub_audio) < target_total_duration_ms:
        dub_audio += AudioSegment.silent(duration=(target_total_duration_ms - len(dub_audio)))

    dub_audio.export(output_wav, format="wav")
    print("\rExport terminé")

    return output_wav
