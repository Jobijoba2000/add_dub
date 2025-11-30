import sys
import json
import os
import logging

# Configure logging for the worker
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger("TranslateWorker")

def main():
    if len(sys.argv) < 4:
        log.error("Usage: python translate_worker.py <input_json> <output_json> <target_lang> [source_lang]")
        sys.exit(1)

    input_json = sys.argv[1]
    output_json = sys.argv[2]
    target_lang = sys.argv[3]
    source_lang = sys.argv[4] if len(sys.argv) > 4 else None

    log.info(f"Worker started. Target: {target_lang}, Source: {source_lang}")

    try:
        with open(input_json, 'r', encoding='utf-8') as f:
            texts = json.load(f)
    except Exception as e:
        log.error(f"Failed to read input JSON: {e}")
        sys.exit(1)

    if not texts:
        log.info("No texts to translate.")
        with open(output_json, 'w', encoding='utf-8') as f:
            json.dump([], f)
        sys.exit(0)

    # Load EasyNMT
    try:
        # Ensure NLTK data is available
        import nltk
        try:
            nltk.data.find('tokenizers/punkt')
        except LookupError:
            nltk.download('punkt')
        try:
            nltk.data.find('tokenizers/punkt_tab')
        except LookupError:
            nltk.download('punkt_tab')

        from easynmt import EasyNMT
        log.info("Loading EasyNMT model (opus-mt) on CPU...")
        model = EasyNMT('opus-mt', device='cpu')
    except Exception as e:
        log.error(f"Failed to load EasyNMT: {e}")
        sys.exit(1)

    # Translate
    translated_texts = []
    
    # Batching logic
    batch_size = 5
    total = len(texts)
    
    for i in range(0, total, batch_size):
        batch = texts[i : i + batch_size]
        # Clean batch
        clean_batch = [str(t) if t else "" for t in batch]
        
        try:
            res = model.translate(clean_batch, target_lang=target_lang, source_lang=source_lang, show_progress_bar=False)
            if isinstance(res, str):
                res = [res]
            translated_texts.extend(res)
        except Exception as e:
            log.error(f"Batch translation failed: {e}")
            # Fallback to original text for this batch
            translated_texts.extend(clean_batch)
        
        percent = min(100, int((i + len(batch)) / total * 100))
        print(f"PROGRESS:{percent}", flush=True) # Special marker for parent process

    # Write output
    try:
        with open(output_json, 'w', encoding='utf-8') as f:
            json.dump(translated_texts, f, ensure_ascii=False)
        log.info("Output written successfully.")
    except Exception as e:
        log.error(f"Failed to write output JSON: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
