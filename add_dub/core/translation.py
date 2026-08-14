
import os
import sys
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
    """
    model_name = f"Helsinki-NLP/opus-mt-{source_lang}-{target_lang}"
    cache_dir = os.path.join(os.path.expanduser("~"), ".cache", "add_dub", "ct2_models")
    model_dir = os.path.join(cache_dir, f"opus-mt-{source_lang}-{target_lang}")

    key = f"{source_lang}_{target_lang}"
    if key in _TRANSLATOR_CACHE:
        return _TRANSLATOR_CACHE[key]

    src_spm = os.path.join(model_dir, "source.spm")
    tgt_spm = os.path.join(model_dir, "target.spm")

    if not os.path.exists(os.path.join(model_dir, "model.bin")) or not os.path.exists(src_spm) or not os.path.exists(tgt_spm):
        os.makedirs(model_dir, exist_ok=True)
        log.info(f"Conversion / chargement du modèle CTranslate2 ({source_lang} -> {target_lang})...")
        conv = ctranslate2.converters.TransformersConverter(model_name)
        conv.convert(model_dir, quantization="int8", force=True)

        from huggingface_hub import hf_hub_download
        try:
            hf_hub_download(repo_id=model_name, filename="source.spm", local_dir=model_dir)
            hf_hub_download(repo_id=model_name, filename="target.spm", local_dir=model_dir)
        except Exception as e:
            log.warning(f"Note: téléchargeur SPM: {e}")

    log.info(f"Chargement du moteur CTranslate2 ({model_name})...")
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
) -> List[Tuple[float, float, str]]:
    """
    Traduit une liste de sous-titres (start, end, text) vers la langue cible via CTranslate2 + SentencePiece.
    """
    texts = [s[2] for s in subtitles]
    if not texts:
        return subtitles

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

    log.info(t("trans_log_start", count=len(texts), target=target_lang, source=source_lang))

    try:
        translator, sp_src, sp_tgt = _get_translator_and_tokenizer(source_lang, target_lang)
    except Exception as e:
        log.error(f"Erreur d'initialisation du traducteur pour {source_lang}->{target_lang}: {e}")
        return subtitles

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
