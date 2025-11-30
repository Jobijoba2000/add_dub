# add_dub/workers.py
import os
import uuid
import add_dub.io.fs as io_fs
from add_dub.core.tts_registry import normalize_engine
from add_dub.i18n import t

def tts_worker(args):
    """
    args: (idx, start_ms, end_ms, text, voice_id, opts)
    - On choisit le moteur depuis opts.tts_engine (fallback 'onecore').
    - On tente la synthèse avec ce moteur.
    - En cas d'échec (exception), on bascule en **fallback** OneCore + voix par défaut système.
    """
    idx, start_ms, end_ms, text, voice_id, opts = args
    
    engine = normalize_engine(getattr(opts, "tts_engine", None))
    
    # Sélection de la fonction synthèse selon le moteur
    try:
        if engine == "onecore":
            from add_dub.core.tts import synthesize_tts_for_subtitle as _synth
        elif engine == "edge":
            from add_dub.core.tts_edge import synthesize_tts_for_subtitle as _synth
        elif engine == "gtts":
            from add_dub.core.tts_gtts import synthesize_tts_for_subtitle as _synth
        else:
            # Sécurité : valeur inconnue → onecore
            from add_dub.core.tts import synthesize_tts_for_subtitle as _synth

        target_duration_ms = end_ms - start_ms
        seg = _synth(text, target_duration_ms, voice_id, opts)
        
    except Exception as e:
        print(t("workers_warn_tts_fail", engine=engine, e=e))
        # Fallback OneCore
        from add_dub.core.tts import synthesize_tts_for_subtitle as _synth_fallback
        target_duration_ms = end_ms - start_ms
        seg = _synth_fallback(text, target_duration_ms, None, opts)

    out_path = os.path.join(io_fs.TMP_DIR, f"dub_seg_{uuid.uuid4().hex}.wav")
    seg.export(out_path, format="wav")
    
    return idx, out_path, start_ms, end_ms
