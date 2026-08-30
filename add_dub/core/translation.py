# add_dub/core/translation.py
from __future__ import annotations

import os
import re
from typing import List, Tuple, Optional, Dict
from add_dub.logger import logger as log
from add_dub.i18n import t
from add_dub.core.ui import UIInterface

import ctranslate2
import sentencepiece

_OPUS_CACHE: Dict[str, Tuple[ctranslate2.Translator, sentencepiece.SentencePieceProcessor, sentencepiece.SentencePieceProcessor]] = {}
_NLLB_CACHE = None

COMMON_INTERJECTIONS = {
    "oh", "ah", "eh", "hein", "ouh", "hey", "chut", "stop", "wow", "ok", "hum", "euh", "pff", "bah"
}

# Alias usuels pour les codes de langues dans les modèles Opus-MT / Hugging Face
OPUS_LANG_VARIANTS: Dict[str, List[str]] = {
    "ja": ["ja", "jap", "jpn"],
    "zh": ["zh", "zho", "chi"],
    "fr": ["fr", "fra", "fre"],
    "de": ["de", "deu", "ger"],
    "es": ["es", "spa"],
    "it": ["it", "ita"],
    "ru": ["ru", "rus"],
    "ar": ["ar", "ara"],
    "el": ["el", "ell", "grk", "gre"],
    "cs": ["cs", "ces", "cze"],
    "ro": ["ro", "ron", "rum"],
    "nl": ["nl", "nld", "dut"],
    "sv": ["sv", "swe"],
    "pt": ["pt", "por"],
    "ko": ["ko", "kor"],
    "vi": ["vi", "vie"],
    "tr": ["tr", "tur"],
    "pl": ["pl", "pol"],
    "da": ["da", "dan"],
    "fi": ["fi", "fin"],
    "no": ["no", "nob", "nor"],
    "hi": ["hi", "hin"],
    "id": ["id", "ind"],
    "th": ["th", "tha"],
    "he": ["he", "heb"],
    "uk": ["uk", "ukr"],
    "bg": ["bg", "bul"],
    "hr": ["hr", "hrv"],
    "sk": ["sk", "slk"],
    "sl": ["sl", "slv"],
    "hu": ["hu", "hun"],
}

# Dépôts spécialisés additionnels pour certaines paires majeures
SPECIAL_PAIRS_REPOS: Dict[str, List[str]] = {
    "en-ja": ["jkawamoto/fugumt-en-ja-ct2", "manancode/opus-mt-en-jap-ctranslate2-android"],
    "ja-en": ["jkawamoto/fugumt-ja-en-ct2", "gaudi/opus-mt-jap-en-ctranslate2", "manancode/opus-mt-ja-en-ctranslate2-android"],
    "ja-fr": ["manancode/opus-mt-ja-fr-ctranslate2-android"],
}

NLLB_LANG_CODES: Dict[str, str] = {
    "fr": "fra_Latn",
    "fra": "fra_Latn",
    "fre": "fra_Latn",
    "en": "eng_Latn",
    "eng": "eng_Latn",
    "es": "spa_Latn",
    "spa": "spa_Latn",
    "de": "deu_Latn",
    "deu": "deu_Latn",
    "ger": "deu_Latn",
    "it": "ita_Latn",
    "ita": "ita_Latn",
    "pt": "por_Latn",
    "por": "por_Latn",
    "ja": "jpn_Jpan",
    "jpn": "jpn_Jpan",
    "zh": "zho_Hans",
    "zho": "zho_Hans",
    "chi": "zho_Hans",
    "ru": "rus_Cyrl",
    "rus": "rus_Cyrl",
    "ar": "ara_Arab",
    "ara": "ara_Arab",
    "nl": "nld_Latn",
    "nld": "nld_Latn",
    "dut": "nld_Latn",
    "pl": "pol_Latn",
    "pol": "pol_Latn",
    "ko": "kor_Hang",
    "kor": "kor_Hang",
    "tr": "tur_Latn",
    "tur": "tur_Latn",
    "uk": "ukr_Cyrl",
    "ukr": "ukr_Cyrl",
    "sv": "swe_Latn",
    "swe": "swe_Latn",
    "cs": "ces_Latn",
    "ces": "ces_Latn",
    "cze": "ces_Latn",
    "el": "ell_Grek",
    "ell": "ell_Grek",
    "gre": "ell_Grek",
    "da": "dan_Latn",
    "dan": "dan_Latn",
    "fi": "fin_Latn",
    "fin": "fin_Latn",
    "no": "nob_Latn",
    "nob": "nob_Latn",
    "nor": "nob_Latn",
    "hi": "hin_Deva",
    "hin": "hin_Deva",
    "vi": "vie_Latn",
    "vie": "vie_Latn",
    "id": "ind_Latn",
    "ind": "ind_Latn",
    "th": "tha_Thai",
    "tha": "tha_Thai",
    "ro": "ron_Latn",
    "ron": "ron_Latn",
    "rum": "ron_Latn",
    "hu": "hun_Latn",
    "hun": "hun_Latn",
    "bg": "bul_Cyrl",
    "bul": "bul_Cyrl",
    "ca": "cat_Latn",
    "cat": "cat_Latn",
    "hr": "hrv_Latn",
    "hrv": "hrv_Latn",
    "sk": "slk_Latn",
    "slk": "slk_Latn",
    "sl": "slv_Latn",
    "slv": "slv_Latn",
    "he": "heb_Hebr",
    "heb": "heb_Hebr",
    "fa": "pes_Arab",
    "pes": "pes_Arab",
    "ur": "urd_Arab",
    "urd": "urd_Arab",
    "bn": "ben_Beng",
    "ben": "ben_Beng",
    "ta": "tam_Taml",
    "tam": "tam_Taml",
    "te": "tel_Telu",
    "tel": "tel_Telu",
    "ms": "zsm_Latn",
    "zsm": "zsm_Latn",
    "sr": "srp_Cyrl",
    "srp": "srp_Cyrl",
    "lt": "lit_Latn",
    "lit": "lit_Latn",
    "lv": "lvs_Latn",
    "lvs": "lvs_Latn",
    "et": "est_Latn",
    "est": "est_Latn",
    "af": "afr_Latn",
    "afr": "afr_Latn",
    "sw": "swh_Latn",
    "swh": "swh_Latn",
}


def normalize_nllb_code(lang: str) -> str:
    clean = str(lang).strip().lower().replace("-", "_")
    if clean in NLLB_LANG_CODES:
        return NLLB_LANG_CODES[clean]
    short = clean[:2]
    if short in NLLB_LANG_CODES:
        return NLLB_LANG_CODES[short]
    if "_" in clean and len(clean) >= 8:
        parts = clean.split("_")
        return f"{parts[0].lower()}_{parts[1].capitalize()}"
    return "eng_Latn"


def _get_opus_translator_and_tokenizer(src: str, tgt: str) -> Optional[Tuple[ctranslate2.Translator, sentencepiece.SentencePieceProcessor, sentencepiece.SentencePieceProcessor]]:
    """
    Charge ou télécharge un modèle bilingue Opus-MT pré-converti pour CTranslate2.
    Gère les variantes de codes de langue (ex: ja/jap/jpn) et les dépôts spécialisés (FuguMT, Gaudi, Manancode, MichaelFeil).
    """
    key = f"{src}_{tgt}"
    if key in _OPUS_CACHE:
        return _OPUS_CACHE[key]

    cache_base = os.path.join(os.path.expanduser("~"), ".cache", "add_dub", "ct2_models")
    from huggingface_hub import snapshot_download

    candidate_repos = []

    # 1. Paires spéciales prioritaires (ex: en-ja via FuguMT / Manancode)
    spec_key = f"{src}-{tgt}"
    if spec_key in SPECIAL_PAIRS_REPOS:
        for r in SPECIAL_PAIRS_REPOS[spec_key]:
            clean_name = r.replace("/", "-")
            candidate_repos.append((r, os.path.join(cache_base, clean_name)))

    # 2. Génération des variantes de codes de langues (ex: en-ja, en-jap, fr-es, etc.)
    src_vars = OPUS_LANG_VARIANTS.get(src, [src])
    tgt_vars = OPUS_LANG_VARIANTS.get(tgt, [tgt])

    for s in src_vars:
        for t_code in tgt_vars:
            pair = f"{s}-{t_code}"
            candidate_repos.extend([
                (f"WindyWord/translate-windy-hplt-{s}-{t_code}", os.path.join(cache_base, f"windy-{pair}")),
                (f"michaelfeil/ct2fast-opus-mt-{pair}", os.path.join(cache_base, f"ct2fast-opus-mt-{pair}")),
                (f"gaudi/opus-mt-{pair}-ctranslate2", os.path.join(cache_base, f"gaudi-opus-mt-{pair}")),
                (f"manancode/opus-mt-{pair}-ctranslate2-android", os.path.join(cache_base, f"manancode-opus-mt-{pair}")),
                (f"manancode/opus-mt-{pair}-ctranslate2", os.path.join(cache_base, f"manancode-opus-mt-{pair}")),
            ])

    for repo_id, model_dir in candidate_repos:
        model_bin = os.path.join(model_dir, "model.bin")
        src_spm = os.path.join(model_dir, "source.spm")
        tgt_spm = os.path.join(model_dir, "target.spm")

        # Modèle déjà en cache local
        if os.path.exists(model_bin) and os.path.exists(src_spm) and os.path.exists(tgt_spm):
            try:
                translator = ctranslate2.Translator(model_dir, device="cpu", compute_type="int8", intra_threads=4)
                sp_src = sentencepiece.SentencePieceProcessor(model_file=src_spm)
                sp_tgt = sentencepiece.SentencePieceProcessor(model_file=tgt_spm)
                _OPUS_CACHE[key] = (translator, sp_src, sp_tgt)
                return _OPUS_CACHE[key]
            except Exception:
                pass

        # Téléchargement depuis Hugging Face
        try:
            log.info(f"Recherche du modèle bilingue {repo_id}...")
            snapshot_download(repo_id=repo_id, local_dir=model_dir)
            if os.path.exists(model_bin) and os.path.exists(src_spm) and os.path.exists(tgt_spm):
                translator = ctranslate2.Translator(model_dir, device="cpu", compute_type="int8", intra_threads=4)
                sp_src = sentencepiece.SentencePieceProcessor(model_file=src_spm)
                sp_tgt = sentencepiece.SentencePieceProcessor(model_file=tgt_spm)
                _OPUS_CACHE[key] = (translator, sp_src, sp_tgt)
                return _OPUS_CACHE[key]
        except Exception:
            try:
                import shutil
                shutil.rmtree(model_dir, ignore_errors=True)
            except Exception:
                pass
            continue

    return None


def _translate_with_opus_pair(texts: List[str], src: str, tgt: str) -> Optional[List[str]]:
    """
    Traduit une liste de textes avec un modèle Opus-MT direct (src -> tgt).
    """
    res = _get_opus_translator_and_tokenizer(src, tgt)
    if res is None:
        return None

    translator, sp_src, sp_tgt = res
    translated = []
    batch_size = 32

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        tokens = [
            sp_src.encode(str(t), out_type=str) + ["</s>"] if t and str(t).strip() else []
            for t in batch
        ]
        try:
            results = translator.translate_batch(tokens)
            for j, r in enumerate(results):
                if r.hypotheses:
                    decoded = sp_tgt.decode(r.hypotheses[0]).strip()
                    translated.append(decoded if decoded else batch[j])
                else:
                    translated.append(batch[j])
        except Exception as e:
            log.error(f"Erreur Opus-MT batch : {e}")
            translated.extend(batch)

    return translated


def _translate_with_opus_pivot(texts: List[str], src: str, tgt: str) -> Optional[List[str]]:
    """
    Traduit via le pivot anglais avec Opus-MT (src -> en -> tgt) : rapide, strict et sans hallucination.
    """
    log.info(f"Traduction stricte via pivot Opus-MT ({src} -> en -> {tgt})...")
    # Étape 1 : src -> en
    en_texts = _translate_with_opus_pair(texts, src, "en")
    if en_texts is None:
        return None

    # Étape 2 : en -> tgt
    tgt_texts = _translate_with_opus_pair(en_texts, "en", tgt)
    return tgt_texts


def _get_nllb_translator_and_tokenizer():
    global _NLLB_CACHE
    if _NLLB_CACHE is not None:
        return _NLLB_CACHE

    cache_dir = os.path.join(os.path.expanduser("~"), ".cache", "add_dub", "ct2_models", "nllb-200-600M-int8")
    model_bin = os.path.join(cache_dir, "model.bin")
    spm_model = os.path.join(cache_dir, "sentencepiece.bpe.model")

    if not (os.path.exists(model_bin) and os.path.exists(spm_model)):
        log.info("Téléchargement du modèle universel NLLB-200...")
        from huggingface_hub import snapshot_download
        repo_id = "osa911/nllb-200-distilled-600M-ct2-int8"
        snapshot_download(repo_id=repo_id, local_dir=cache_dir)

    translator = ctranslate2.Translator(cache_dir, device="cpu", compute_type="int8", intra_threads=4)
    sp_model = sentencepiece.SentencePieceProcessor(model_file=spm_model)
    _NLLB_CACHE = (translator, sp_model)
    return _NLLB_CACHE


def _translate_with_nllb(texts: List[str], src_lang: str, tgt_lang: str) -> List[str]:
    """
    Traduction universelle via NLLB-200 avec garde-fou anti-hallucination sur les petits mots.
    """
    src_nllb = normalize_nllb_code(src_lang)
    tgt_nllb = normalize_nllb_code(tgt_lang)

    translator, sp_model = _get_nllb_translator_and_tokenizer()
    translated_texts = []
    batch_size = 16

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        tokens = []
        for text in batch:
            clean_str = str(text).strip() if text else ""
            if clean_str:
                encoded = [src_nllb] + sp_model.encode(clean_str, out_type=str) + ["</s>"]
                tokens.append(encoded)
            else:
                tokens.append([])

        try:
            target_prefix = [[tgt_nllb]] * len(tokens)
            results = translator.translate_batch(tokens, target_prefix=target_prefix)

            for j, r in enumerate(results):
                original_text = batch[j].strip()
                orig_lower = re.sub(r'[^\w\s]', '', original_text).lower()

                if orig_lower in COMMON_INTERJECTIONS:
                    translated_texts.append(original_text)
                    continue

                if r.hypotheses:
                    hyp = r.hypotheses[0]
                    clean_hyp = [tok for tok in hyp if tok not in (tgt_nllb, src_nllb, "</s>", "<s>", "<unk>")]
                    decoded = sp_model.decode(clean_hyp).strip()

                    if len(original_text.split()) == 1 and len(decoded.split()) >= 4:
                        translated_texts.append(original_text)
                    else:
                        translated_texts.append(decoded if decoded else original_text)
                else:
                    translated_texts.append(original_text)
        except Exception as e:
            log.error(f"Erreur NLLB batch : {e}")
            translated_texts.extend(batch)

    return translated_texts


def translate_subtitles(
    subtitles: List[Tuple[float, float, str]], 
    target_lang: str, 
    source_lang: Optional[str] = None,
    ui: Optional[UIInterface] = None
) -> Optional[List[Tuple[float, float, str]]]:
    """
    Traduit les sous-titres :
    1. Recherche un modèle Opus-MT direct dans tous les dépôts CTranslate2.
    2. Si aucun modèle direct n'existe, passe par le pivot Opus-MT anglais (src -> en -> tgt).
    3. Secours universel NLLB-200 avec filtres anti-hallucination.
    """
    texts = [s[2] for s in subtitles]
    if not texts:
        return subtitles

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
    tgt = str(target_lang).strip().lower()[:2]

    if src == tgt:
        log.info(t("pipeline_trans_same_lang_skip", src=src, tgt=tgt))
        return subtitles

    log.info(f"Traduction de {len(texts)} sous-titres ({src} -> {tgt})...")
    if ui:
        ui.message(f"Traduction des sous-titres ({src} -> {tgt})...")

    # Stratégie 1 : Opus-MT direct multi-dépôts (gaudi, michaelfeil, manancode, fugumt)
    translated_texts = _translate_with_opus_pair(texts, src, tgt)

    # Stratégie 2 : Pivot anglais Opus-MT
    if translated_texts is None and src != "en" and tgt != "en":
        translated_texts = _translate_with_opus_pivot(texts, src, tgt)

    # Stratégie 3 : Secours NLLB-200
    if translated_texts is None:
        log.info(f"Passage au modèle universel NLLB-200 ({src} -> {tgt})...")
        translated_texts = _translate_with_nllb(texts, src, tgt)

    new_subs = []
    for i, (start, end, _) in enumerate(subtitles):
        if i < len(translated_texts):
            new_subs.append((start, end, translated_texts[i]))
        else:
            new_subs.append((start, end, subtitles[i][2]))

    log.info(t("trans_log_completed"))
    return new_subs


def write_srt_file(subtitles: List[Tuple[float, float, str]], output_path: str):
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
