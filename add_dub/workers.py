# add_dub/workers.py
import os
import tempfile
import uuid


def tts_worker(args):
    # Import local pour éviter les soucis de pickling/multiprocessing sous Windows
    from add_dub.core.tts import synthesize_tts_for_subtitle

    idx, start_ms, end_ms, text, voice_id = args
    duration = end_ms - start_ms
    seg = synthesize_tts_for_subtitle(text, duration, voice_id)

    out_path = os.path.join(tempfile.gettempdir(), f"dub_seg_{uuid.uuid4().hex}.wav")
    seg.export(out_path, format="wav")
    return idx, out_path, start_ms, end_ms
