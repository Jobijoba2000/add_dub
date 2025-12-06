
import os


import sys
import json
import subprocess
import tempfile
from typing import List, Tuple, Optional
from add_dub.logger import logger as log
from add_dub.i18n import t
from add_dub.core.ui import UIInterface

# Note: We no longer import EasyNMT here to avoid crashes in the main process.

def translate_subtitles(
    subtitles: List[Tuple[float, float, str]], 
    target_lang: str, 
    source_lang: str = None,
    ui: Optional[UIInterface] = None
) -> List[Tuple[float, float, str]]:
    """
    Traduit une liste de sous-titres (start, end, text) vers la langue cible.
    Exécute la traduction dans un sous-processus isolé pour éviter les crashs (PyTorch/Windows).
    """
    texts = [s[2] for s in subtitles]
    if not texts:
        return subtitles

    log.info(t("trans_log_start", count=len(texts), target=target_lang, source=source_lang))

    # Create temp files for IPC
    with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8', suffix='.json') as f_in:
        json.dump(texts, f_in, ensure_ascii=False)
        input_path = f_in.name
    
    # Output file path
    output_path = input_path + ".out.json"

    worker_script = os.path.join(os.path.dirname(__file__), "translate_worker.py")
    
    cmd = [
        sys.executable, 
        worker_script,
        input_path,
        output_path,
        target_lang
    ]
    if source_lang:
        cmd.append(source_lang)

    try:
        # Run subprocess and capture output for progress
        # Merge stderr into stdout to avoid deadlock if stderr buffer fills up
        process = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT, 
            text=True,
            encoding='utf-8' # Force encoding
        )
        
        # Read stdout line by line to show progress
        while True:
            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break
            if line:
                line = line.strip()
                if line.startswith("PROGRESS:"):
                    pct = float(line.split(':')[1])
                    if ui:
                        ui.progress(pct)
                    else:
                        # Avoid spamming logs with progress
                        pass
                else:
                    # Log other output (logs, warnings) as debug info
                    # This ensures we drain the buffer and don't deadlock
                    if line:
                        log.debug(f"Worker: {line}")

        # No stderr to read since it's merged
        stdout, _ = process.communicate()
        
        if process.returncode != 0:
            log.error(t("trans_err_subprocess", code=process.returncode))
            return subtitles

        # Read result
        if os.path.exists(output_path):
            with open(output_path, 'r', encoding='utf-8') as f_out:
                translated_texts = json.load(f_out)
        else:
            log.error(t("trans_err_no_output"))
            return subtitles

    except Exception as e:
        log.error(t("trans_err_exception", err=e))
        return subtitles
    finally:
        # Cleanup
        if os.path.exists(input_path):
            os.remove(input_path)
        if os.path.exists(output_path):
            os.remove(output_path)

    # if not ui:
    #     print("") # Newline after progress
    log.info(t("trans_log_completed"))

    new_subs = []
    for i, (start, end, _) in enumerate(subtitles):
        if i < len(translated_texts):
            new_text = translated_texts[i]
            new_subs.append((start, end, new_text))
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
