# add_dub/workers.py
import os
import tempfile
import uuid

from add_dub.core.tts_registry import normalize_engine, resolve_voice_with_fallbacks


def tts_worker(args):
    """
    args: (idx, start_ms, end_ms, text, voice_id, opts)
    - On choisit le moteur depuis opts.tts_engine (fallback 'onecore').
    - On tente la synthèse avec ce moteur.
    - En cas d'échec (exception), on bascule en **fallback** OneCore + voix par défaut système.
    """
    idx, start_ms, end_ms, text, voice_id, opts = args
    duration = end_ms - start_ms

    engine = normalize_engine(getattr(opts, "tts_engine", None))
    chosen_voice = voice_id

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
            engine = "onecore"
            from add_dub.core.tts import synthesize_tts_for_subtitle as _synth

        seg = _synth(text, duration, chosen_voice, opts)

    except Exception as e:
        # Fallback global OneCore + voix système
        print(f"[WARN] Synthèse '{engine}' a échoué ({e}). Fallback OneCore/voix système.")
        from add_dub.core.tts import synthesize_tts_for_subtitle as _synth_one
        # Resolve sans préférence de langue (registry va retourner la voix système OneCore)
        fallback_voice = resolve_voice_with_fallbacks(engine="onecore", desired_voice_id=None, preferred_lang_base=None)
        if fallback_voice is None:
            raise RuntimeError("Aucune voix OneCore disponible pour fallback.") from e
        seg = _synth_one(text, duration, fallback_voice, opts)

    # en tête du fichier
    import add_dub.io.fs as io_fs

    # à l’endroit de l’export
    out_path = os.path.join(io_fs.TMP_DIR, f"dub_seg_{uuid.uuid4().hex}.wav")

    seg.export(out_path, format="wav")
    return idx, out_path, start_ms, end_ms
