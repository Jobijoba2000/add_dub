"""Un travail vocal borné, sans changement silencieux de moteur ou de voix."""
import os
import uuid
import time
from add_dub.core.tts_registry import normalize_engine
from add_dub.io.work import CURRENT
from add_dub.io import fs


def tts_worker(args):
    idx, start_ms, end_ms, text, voice_id, opts = args
    token = CURRENT.set(opts.work_dir)
    try:
        engine = normalize_engine(opts.tts_engine)
        if opts.offline and engine != 'onecore':
            raise ValueError('Le mode hors ligne interdit la synthèse distante.')
        if engine == 'edge':
            from add_dub.core.tts_edge import synthesize_tts_for_subtitle as synth
        elif engine == 'gtts':
            from add_dub.core.tts_gtts import synthesize_tts_for_subtitle as synth
        else:
            from add_dub.core.tts import synthesize_tts_for_subtitle as synth
        for attempt in range(2):
            try:
                result = synth(text, end_ms - start_ms, voice_id, opts)
                break
            except Exception:
                if attempt == 1 or engine == 'onecore':
                    raise
                time.sleep(.5)
        segment = result[0] if isinstance(result, tuple) else result
        path = os.path.join(fs.get_tmp_dir(), f'dub_seg_{uuid.uuid4().hex}.wav')
        segment.set_sample_width(2).export(path, format='wav')
        return idx, path, start_ms, end_ms
    finally:
        CURRENT.reset(token)
