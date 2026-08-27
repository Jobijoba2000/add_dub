
import os
from typing import List, Tuple, Optional
from add_dub.logger import logger as log
from add_dub.i18n import t
from add_dub.core.ui import UIInterface

import ctranslate2
import sentencepiece

_TRANSLATOR_CACHE = {}


def _get_translator_and_tokenizer(source_lang: str, target_lang: str):
    """
    Retourne le traducteur CTranslate2 et les tokenizers SentencePiece pour la paire de langues.
    Télécharge automatiquement le modèle CTranslate2 pré-converti si non présent dans le cache.
    """
    src = str(source_lang).strip().lower()[:2]
    tgt = str(target_lang).strip().lower()[:2]
    if src == tgt:
        raise ValueError(f"Source and target languages are identical: {src}")

    pair_name = f"{src}-{tgt}"
    cache_dir = os.path.join(os.path.expanduser("~"), ".cache", "add_dub", "ct2_models")
    model_dir = os.path.join(cache_dir, f"ct2fast-opus-mt-{pair_name}")

    key = f"{src}_{tgt}"
    if key in _TRANSLATOR_CACHE:
        return _TRANSLATOR_CACHE[key]

    src_spm = os.path.join(model_dir, "source.spm")
    tgt_spm = os.path.join(model_dir, "target.spm")
    model_bin = os.path.join(model_dir, "model.bin")

    # Si le modèle n'est pas présent dans le cache, le télécharger automatiquement depuis HuggingFace
    if not (os.path.exists(model_bin) and os.path.exists(src_spm) and os.path.exists(tgt_spm)):
        os.makedirs(model_dir, exist_ok=True)
        log.info(f"Téléchargement automatique du modèle CTranslate2 ({src} -> {tgt})...")
        from huggingface_hub import snapshot_download
        repo_id = f"michaelfeil/ct2fast-opus-mt-{src}-{tgt}"
        try:
            snapshot_download(repo_id=repo_id, local_dir=model_dir)
        except Exception as e:
            # Nettoyer le dossier vide pour ne pas corrompre le cache
            try:
                import shutil
                shutil.rmtree(model_dir, ignore_errors=True)
            except Exception:
                pass
            log.error(f"Échec du téléchargement du modèle pré-converti {repo_id}: {e}")
            raise RuntimeError(f"Impossible de télécharger le modèle de traduction pour {src}->{tgt}: {e}")

    log.info(f"Chargement du moteur CTranslate2 ({src} -> {tgt})...")
    translator = ctranslate2.Translator(model_dir, device="cpu", intra_threads=1)

    sp_src = sentencepiece.SentencePieceProcessor(model_file=src_spm)
    sp_tgt = sentencepiece.SentencePieceProcessor(model_file=tgt_spm)

    _TRANSLATOR_CACHE[key] = (translator, sp_src, sp_tgt)
    return translator, sp_src, sp_tgt


def translate_subtitles(
    subtitles: List[Tuple[float, float, str]], 
    target_lang: str, 
    source_lang: Optional[str] = None,
    ui: Optional[UIInterface] = None
) -> Optional[List[Tuple[float, float, str]]]:
    """
    Traduit une liste de sous-titres (start, end, text) vers la langue cible via CTranslate2 + SentencePiece.
    Retourne la liste traduite ou None en cas d'échec / modèle inexistant.
    """
    texts = [s[2] for s in subtitles]
    if not texts:
        return subtitles

    tgt = str(target_lang).strip().lower()[:2]

    # Auto-détection de la langue source si non fournie ou 'auto'
    if not source_lang or source_lang.lower() == "auto":
        try:
            from langdetect import detect
            sample = " ".join([str(t) for t in texts[:10] if t])
            if sample:
                source_lang = detect(sample)
                log.info(f"Langue source détectée : {source_lang}")
        except Exception as e:
            log.warning(f"Échec de détection de langue : {e}")
            source_lang = "fr"

    src = str(source_lang).strip().lower()[:2]

    # Court-circuit si source == cible
    if src == tgt:
        log.info(t("pipeline_trans_same_lang_skip", src=src, tgt=tgt))
        return subtitles

    log.info(t("trans_log_start", count=len(texts), target=tgt, source=src))

    try:
        translator, sp_src, sp_tgt = _get_translator_and_tokenizer(src, tgt)
    except Exception as e:
        log.error(f"Erreur d'initialisation du traducteur pour {src}->{tgt}: {e}")
        return None

    translated_texts = []
    batch_size = 16
    total = len(texts)

    for i in range(0, total, batch_size):
        batch = texts[i : i + batch_size]
        tokens = [
            sp_src.encode(str(t), out_type=str) + ["</s>"] if t and str(t).strip() else []
            for t in batch
        ]

        try:
            results = translator.translate_batch(tokens)
            for j, r in enumerate(results):
                if r.hypotheses:
                    decoded = sp_tgt.decode(r.hypotheses[0])
                    translated_texts.append(decoded)
                else:
                    translated_texts.append(batch[j])
        except Exception as e:
            log.error(f"Erreur lors de la traduction d'un lot : {e}")
            translated_texts.extend(batch)

        pct = min(100.0, int((i + len(batch)) / total * 100))
        if ui:
            ui.progress(pct)

    log.info(t("trans_log_completed"))

    new_subs = []
    for i, (start, end, _) in enumerate(subtitles):
        if i < len(translated_texts):
            new_subs.append((start, end, translated_texts[i]))
        else:
            new_subs.append((start, end, subtitles[i][2]))

    return new_subs


def write_srt_file(subtitles: List[Tuple[float, float, str]], output_path: str):
    """
    Écrit une liste de sous-titres dans un fichier SRT.
    """
    def format_timestamp(seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds - int(seconds)) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    with open(output_path, "w", encoding="utf-8") as f:
        for i, (start, end, text) in enumerate(subtitles, 1):
            f.write(f"{i}\n")
            f.write(f"{format_timestamp(start)} --> {format_timestamp(end)}\n")
            f.write(f"{text}\n\n")
