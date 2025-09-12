import os
import re
import html
import subprocess
import json
import sys
import time
import tempfile
import uuid
import shutil
from pydub import AudioSegment
import pyttsx3

# =================== Dossiers I/O ===================

INPUT_DIR = os.path.join(os.getcwd(), "input")
OUTPUT_DIR = os.path.join(os.getcwd(), "output")
TMP_DIR = os.path.join(os.getcwd(), "tmp")
os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(TMP_DIR, exist_ok=True)

# Forcer le dossier temporaire
os.environ["TEMP"] = TMP_DIR
os.environ["TMP"] = TMP_DIR

# =================== Réglages globaux ===================

# Choix du codec audio final : "aac", "mp3", "ac3", "flac", "opus", "vorbis", "pcm_s16le"
AUDIO_CODEC_FINAL = "ac3"      # <- change ici

# Bitrate optionnel (ex: "192k"). Laisser None pour laisser ffmpeg choisir.
# (Ignoré pour les codecs sans pertes comme "flac" et "pcm_s16le")
AUDIO_BITRATE = "320k"         # ex: "192k" ou None

# =================== Réglages par défaut (écrasés par questions) ===================

BG_MIX = 1.0    # niveau de l'audio de fond (low_audio), 1.0 = inchangé
TTS_MIX = 1.0   # niveau de la voix TTS (dub), 1.0 = inchangé
DB_REDUCT = -5.0
OFFSET_STR = 0  # ms

# Conserver la constante, ne pas l'utiliser (placeholder historique)
FILTER_CHAIN = "afftdn=nr=8,loudnorm=I=-14:TP=-1.0:LRA=7,afade=t=in:st=0:d=0.06"

# Numpy (optionnel)
try:
    import numpy as np
except ImportError:
    np = None

from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from multiprocessing import cpu_count

# Pour créer des raccourcis sous Windows (facultatif)
try:
    import win32com.client
except ImportError:
    win32com = None


# =================== Helpers formats/sorties ===================

def _final_audio_ext():
    codec = AUDIO_CODEC_FINAL.lower()
    if codec == "aac":
        return ".m4a"
    if codec == "mp3":
        return ".mp3"
    if codec == "ac3":
        return ".ac3"
    if codec == "flac":
        return ".flac"
    if codec == "opus":
        return ".opus"
    if codec == "vorbis":
        return ".ogg"
    if codec == "pcm_s16le":
        return ".wav"
    return ".m4a"

def _final_video_ext():
    # MP4 si AAC (pour compatibilité), sinon MKV
    return ".mp4" if AUDIO_CODEC_FINAL.lower() in ("aac",) else ".mkv"

def _subtitle_codec_for_container():
    # MP4 ne supporte pas SRT -> mov_text ; MKV -> srt
    return "mov_text" if _final_video_ext() == ".mp4" else "srt"

def _final_audio_codec_args():
    codec = AUDIO_CODEC_FINAL.lower()
    lossy = {"aac", "mp3", "opus", "vorbis", "ac3"}

    if codec == "aac":
        args = ["-c:a", "aac"]
    elif codec == "mp3":
        args = ["-c:a", "libmp3lame"]
    elif codec == "ac3":
        args = ["-c:a", "ac3"]
    elif codec == "flac":
        args = ["-c:a", "flac"]
    elif codec == "opus":
        args = ["-c:a", "libopus"]
    elif codec == "vorbis":
        args = ["-c:a", "libvorbis"]
    elif codec == "pcm_s16le":
        args = ["-c:a", "pcm_s16le"]
    else:
        args = ["-c:a", "aac"]

    if AUDIO_BITRATE and codec in lossy:
        args += ["-b:a", AUDIO_BITRATE]
    return args


# =================== Utilitaires I/O ===================

def _join_input(path):
    return os.path.join(INPUT_DIR, path)

def _join_output(path):
    return os.path.join(OUTPUT_DIR, path)

def find_sidecar_srt(video_path):
    base, _ = os.path.splitext(video_path)
    candidates = [base + ".srt", base + ".SRT"]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None

def _find_exe(candidates):
    for c in candidates:
        p = shutil.which(c)
        if p:
            return p
        if os.path.exists(c):
            return c
    return None

def _mkvmerge_identify_json(video_path):
    mkvmerge = _find_exe([
        "mkvmerge",
        r"C:\Program Files\MKVToolNix\mkvmerge.exe",
        r"C:\Program Files (x86)\MKVToolNix\mkvmerge.exe",
    ])
    if not mkvmerge:
        return None
    try:
        r = subprocess.run([mkvmerge, "-J", video_path],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return json.loads(r.stdout)
    except Exception:
        return None

def mkv_has_subtitle_track(video_path):
    info = _mkvmerge_identify_json(video_path)
    if not info:
        return False
    for t in info.get("tracks", []):
        if t.get("type") == "subtitles":
            return True
    return False

def list_mkv_sub_tracks(video_path):
    info = _mkvmerge_identify_json(video_path)
    tracks = []
    printable = []
    if not info:
        return tracks, printable
    for t in info.get("tracks", []):
        if t.get("type") == "subtitles":
            tid = t.get("id")
            prop = t.get("properties", {}) or {}
            cid = (prop.get("codec_id") or "").lower()
            lang = prop.get("language", "und")
            name = prop.get("track_name", "")
            tracks.append(t)
            printable.append(f"  mkv id={tid} | codec={cid} | lang={lang} | title={name}")
    return tracks, printable

def list_input_videos():
    """
    Retourne les fichiers éligibles situés dans input/ :
    - MKV : affiché si au moins une piste ST intégrée OU SRT sidecar présent.
    - MP4 : affiché seulement si SRT sidecar présent.
    """
    try:
        files = os.listdir(INPUT_DIR)
    except FileNotFoundError:
        files = []
    candidates = []
    for f in files:
        full = _join_input(f)
        if not os.path.isfile(full):
            continue
        fl = f.lower()
        if fl.endswith(".mkv"):
            srt = find_sidecar_srt(full)
            if srt or mkv_has_subtitle_track(full):
                candidates.append(f)
        elif fl.endswith(".mp4"):
            srt = find_sidecar_srt(full)
            if srt:
                candidates.append(f)
    return sorted(candidates, key=lambda x: x.lower())

def choose_files(files):
    if not files:
        print("Aucun fichier éligible trouvé dans input/.")
        sys.exit(1)
    print("\nFichiers éligibles (input/):")
    for idx, f in enumerate(files, start=1):
        print(f"  {idx}. {f}")
    sel = input("Entrez les numéros à traiter (espaces, Entrée=tout) : ").strip()
    if sel == "":
        return files
    try:
        indices = [int(x) for x in sel.split() if x.isdigit() and 1 <= int(x) <= len(files)]
        return [files[i - 1] for i in indices]
    except Exception:
        print("Sélection invalide. Traitement de tous les fichiers.")
        return files


# =================== Interactions ===================

def ask_mode():
    ans = input("\nMode (A)uto / (M)anuel ? [A]: ").strip().lower()
    return "manual" if ans.startswith("m") else "auto"

def ask_yes_no(prompt_txt, default_no=True):
    default = "n" if default_no else "o"
    s = input(f"{prompt_txt} (o/n) [{default}]: ").strip().lower()
    if s == "":
        return not default_no
    return s.startswith("o") or s == "y"

def ask_float(prompt_txt, default):
    s = input(f"{prompt_txt} [{default}]: ").strip()
    try:
        return float(s) if s != "" else float(default)
    except:
        print("Valeur invalide, on garde le défaut.")
        return float(default)

def ask_int(prompt_txt, default):
    s = input(f"{prompt_txt} [{default}]: ").strip()
    try:
        return int(s) if s != "" else int(default)
    except:
        print("Valeur invalide, on garde le défaut.")
        return int(default)

def ask_str(prompt_txt, default):
    s = input(f"{prompt_txt} [{default}]: ").strip()
    return s if s != "" else default


# =================== Probes & choix pistes ===================

def get_track_info(video_fullpath):
    cmd = ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", video_fullpath]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    data = json.loads(result.stdout) if result.stdout else {}
    audio_tracks = []
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "audio":
            audio_tracks.append(stream)
    return audio_tracks

def choose_audio_track_ffmpeg_index(video_fullpath):
    tracks = get_track_info(video_fullpath)
    if not tracks:
        print("Aucune piste audio trouvée.")
        sys.exit(1)
    print("\nPistes audio disponibles :")
    for idx, stream in enumerate(tracks, start=0):
        index = stream.get("index")
        tags = stream.get("tags", {}) or {}
        lang = tags.get("language", "und")
        title = tags.get("title", "")
        print(f"  {idx} : ffmpeg index {index}, langue={lang}, titre={title}")
    chosen = input("Numéro de la piste audio à utiliser (défaut 0) : ").strip()
    try:
        chosen_idx = int(chosen) if chosen != "" else 0
        if chosen_idx < 0 or chosen_idx >= len(tracks):
            raise Exception("Numéro invalide")
    except Exception:
        print("Sélection invalide. Fin du programme.")
        sys.exit(1)
    return tracks[chosen_idx].get("index")

def choose_subtitle_source(video_fullpath):
    """
    Affiche TOUTES les sources ST possibles, avec priorité visuelle au SRT sidecar.
    Retourne un tuple:
        ("srt", srt_path)  ou  ("mkv", local_sub_index)
    """
    base, ext = os.path.splitext(video_fullpath)
    sidecar = find_sidecar_srt(video_fullpath)
    choices = []
    labels = []

    if sidecar:
        choices.append(("srt", sidecar))
        labels.append(f"  0 : SRT sidecar -> {os.path.basename(sidecar)}")

    if ext.lower().endswith(".mkv"):
        tracks, printable = list_mkv_sub_tracks(video_fullpath)
        for i, _t in enumerate(tracks):
            local_idx = i
            labels.append(f"  {len(choices)} : {printable[i]}")
            choices.append(("mkv", local_idx))

    if not choices:
        print("Aucune source de sous-titres disponible.")
        return None

    print("\nSources de sous-titres :")
    for line in labels:
        print(line)

    s = input(f"Choisir la source ST (0..{len(choices)-1}) [0]: ").strip()
    try:
        idx = int(s) if s != "" else 0
    except:
        idx = 0
    if idx < 0 or idx >= len(choices):
        idx = 0
    return choices[idx]


# =================== SRT / Parsing ===================

def strip_subtitle_tags_inplace(path: str) -> None:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    blocks = re.split(r"\n\s*\n", content.strip())
    cleaned_blocks = []
    for b in blocks:
        lines = b.splitlines()
        if len(lines) >= 3 and re.match(r'\d{2}:\d{2}:\d{2},\d{3}\s*-->\s*\d{2}:\d{2}:\d{2},\d{3}', lines[1]):
            header = lines[:2]
            text_lines = lines[2:]
            new_text = []
            for t in text_lines:
                t = html.unescape(t)
                t = re.sub(r'<[^>]+>', '', t)
                t = re.sub(r'\{\\[^}]*\}', '', t)
                t = re.sub(r'\s{2,}', ' ', t).strip()
                new_text.append(t)
            new_text = [x for x in new_text if x]
            cleaned_blocks.append("\n".join(header + (new_text or [""])))
        else:
            cleaned_blocks.append(b)
    cleaned = "\n\n".join(cleaned_blocks) + "\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(cleaned)

def time_to_seconds(t_str):
    h, m, s_ms = t_str.split(":")
    s, ms = s_ms.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0

def parse_srt_file(srt_file, duration_limit_sec=None):
    with open(srt_file, encoding="utf-8") as f:
        content = f.read()
    blocks = re.split(r"\n\s*\n", content.strip())
    subtitles = []
    for block in blocks:
        lines = block.splitlines()
        if len(lines) >= 3:
            m = re.match(r'(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d{3})', lines[1])
            if not m:
                continue
            start = time_to_seconds(m.group(1).replace('.', ','))
            end = time_to_seconds(m.group(2).replace('.', ','))
            if duration_limit_sec is not None and start >= duration_limit_sec:
                continue
            if duration_limit_sec is not None and end > duration_limit_sec:
                end = float(duration_limit_sec)
            text = " ".join(lines[2:]).strip()
            subtitles.append((start, end, text))
    return subtitles


# =================== Audio helpers ===================

def extract_audio_track(video_fullpath, audio_track_index, output_wav, duration_sec=None):
    cmd = [
        "ffmpeg", "-y",
        "-hide_banner", "-loglevel", "error", "-stats",
        "-i", video_fullpath,
        "-map", f"0:{audio_track_index}",
        "-vn",
        "-c:a", "pcm_s16le"
    ]
    if duration_sec is not None:
        cmd.extend(["-t", str(int(duration_sec))])
    cmd.append(output_wav)
    start = time.perf_counter()
    subprocess.run(cmd, check=True)
    end = time.perf_counter()
    print(end - start)
    return output_wav


# =================== OPTI ducking ===================

def _pcm_to_numpy(audio: AudioSegment):
    if np is None:
        return None, audio.frame_rate, audio.channels, audio.sample_width, None, None
    sw = audio.sample_width
    ch = audio.channels
    fr = audio.frame_rate
    raw = audio.raw_data
    frame_size = ch * sw
    if len(raw) % frame_size != 0:
        return None, fr, ch, sw, None, None
    n_frames = len(raw) // frame_size
    if sw == 2:
        arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
        arr = arr.reshape(n_frames, ch)
        arr /= 32768.0
        return arr, fr, ch, sw, 32768.0, np.int16
    elif sw == 4:
        arr = np.frombuffer(raw, dtype=np.int32).astype(np.float32)
        arr = arr.reshape(n_frames, ch)
        arr /= 2147483648.0
        return arr, fr, ch, sw, 2147483648.0, np.int32
    elif sw == 1:
        arr = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
        arr = arr.reshape(n_frames, ch)
        arr = (arr - 128.0) / 128.0
        return arr, fr, ch, sw, 128.0, np.uint8
    else:
        return None, fr, ch, sw, None, None

def _numpy_to_pcm(arr_f32, fr, ch, sw, scale, dtype):
    arr = np.clip(arr_f32, -1.0, 1.0)
    if sw in (2, 4):
        out = (arr * scale).astype(dtype).reshape(-1)
        return out.tobytes(), sw
    elif sw == 1:
        out = (arr * scale + 128.0).round().astype(dtype).reshape(-1)
        return out.tobytes(), sw
    else:
        raise ValueError("sample_width non géré")

def lower_audio_during_subtitles(audio_file, subtitles, output_wav, reduction_db=-5.0, fade_duration=100):
    audio = AudioSegment.from_file(audio_file)
    subtitles = sorted(list(subtitles), key=lambda x: x[0])

    env = _pcm_to_numpy(audio)
    if env[0] is None:
        subtitles.sort(key=lambda x: x[0])
        output = AudioSegment.empty()
        current_ms = 0
        for start, end, _ in subtitles:
            start_ms = int(start * 1000 + OFFSET_STR)
            end_ms = int(end * 1000 + OFFSET_STR)
            if end_ms <= 0:
                continue
            if start_ms < 0:
                start_ms = 0
            if end_ms <= start_ms:
                continue
            if start_ms > current_ms:
                output += audio[current_ms:start_ms]
            original_seg = audio[start_ms:end_ms]
            seg_duration = len(original_seg)
            if seg_duration > 2 * fade_duration:
                reduced_seg = original_seg.apply_gain(reduction_db)
                initial_transition = original_seg[:fade_duration].fade_out(fade_duration).overlay(
                    reduced_seg[:fade_duration].fade_in(fade_duration))
                final_transition = reduced_seg[-fade_duration:].fade_out(fade_duration).overlay(
                    original_seg[-fade_duration:].fade_in(fade_duration))
                middle = reduced_seg[fade_duration:seg_duration - fade_duration]
                new_seg = initial_transition + middle + final_transition
            else:
                new_seg = original_seg.apply_gain(reduction_db)
            output += new_seg
            current_ms = end_ms
        if current_ms < len(audio):
            output += audio[current_ms:]
        output.export(output_wav, format="wav")
        return output_wav

    samples_f32, fr, ch, sw, scale, dtype = env
    n_frames = samples_f32.shape[0]
    envelope = np.ones(n_frames, dtype=np.float32)
    gain = 10.0 ** (reduction_db / 20.0)
    fade_frames = max(0, int(round(fade_duration * fr / 1000.0)))
    offset_s = OFFSET_STR / 1000.0

    for start, end, _ in subtitles:
        s = int(round((start + offset_s) * fr))
        e = int(round((end + offset_s) * fr))
        if e <= 0:
            continue
        s = max(0, s)
        e = min(n_frames, e)
        if e <= s:
            continue
        seg_len = e - s
        if seg_len > 2 * fade_frames:
            if fade_frames > 0:
                ramp_down = np.linspace(1.0, gain, fade_frames, dtype=np.float32)
                envelope[s:s + fade_frames] *= ramp_down
            mid_start = s + fade_frames
            mid_end = e - fade_frames
            if mid_end > mid_start:
                envelope[mid_start:mid_end] *= gain
            if fade_frames > 0:
                ramp_up = np.linspace(gain, 1.0, fade_frames, dtype=np.float32)
                envelope[e - fade_frames:e] *= ramp_up
        else:
            envelope[s:e] *= gain

    max_workers = min((os.cpu_count() or 4), 8)
    blocks = max_workers * 4
    block_size = (n_frames + blocks - 1) // blocks

    def _apply_block(b):
        i0 = b * block_size
        i1 = min(n_frames, i0 + block_size)
        if i0 < i1:
            samples_f32[i0:i1, :] *= envelope[i0:i1, None]

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        ex.map(_apply_block, range(blocks))

    raw_bytes, out_sw = _numpy_to_pcm(samples_f32, fr, ch, sw, scale, dtype)
    out_seg = AudioSegment(data=raw_bytes, sample_width=out_sw, frame_rate=fr, channels=ch)
    out_seg.export(output_wav, format="wav")
    return output_wav


# =================== TTS ===================

def get_tts_duration_for_rate(text, rate, voice_id=None):
    engine = pyttsx3.init()
    if voice_id:
        engine.setProperty("voice", voice_id)
    engine.setProperty("rate", rate)
    temp_file = os.path.join(tempfile.gettempdir(), "tts_temp_" + str(uuid.uuid4()) + ".wav")
    engine.save_to_file(text, temp_file)
    engine.runAndWait()
    if os.path.exists(temp_file):
        segment = AudioSegment.from_file(temp_file)
        duration = len(segment)
        try:
            os.remove(temp_file)
        except Exception:
            pass
    else:
        duration = 0
    engine.stop()
    return duration

def find_optimal_rate(text, target_duration_ms, voice_id=None):
    low, high = 200, 360
    candidate = None
    while low <= high:
        mid = (low + high) // 2
        current_duration = get_tts_duration_for_rate(text, mid, voice_id)
        if abs(current_duration - target_duration_ms) <= 100:
            candidate = mid
            break
        if current_duration < target_duration_ms:
            candidate = mid
            high = mid - 10
        else:
            low = mid + 10
    if candidate is None:
        candidate = 200
    return candidate

def synthesize_tts_for_subtitle(text, target_duration_ms, voice_id=None):
    optimal_rate = find_optimal_rate(text, target_duration_ms, voice_id)
    engine = pyttsx3.init()
    if voice_id:
        engine.setProperty("voice", voice_id)
    engine.setProperty("rate", optimal_rate)
    temp_file = os.path.join(tempfile.gettempdir(), "tts_temp_" + str(uuid.uuid4()) + ".wav")
    engine.save_to_file(text, temp_file)
    engine.runAndWait()
    if os.path.exists(temp_file):
        segment = AudioSegment.from_file(temp_file)
    else:
        segment = AudioSegment.silent(duration=0)
    try:
        if os.path.exists(temp_file):
            os.remove(temp_file)
    except Exception:
        pass
    engine.stop()
    if len(segment) > target_duration_ms:
        segment = segment[:target_duration_ms]
    elif len(segment) < target_duration_ms:
        segment = segment + AudioSegment.silent(duration=(target_duration_ms - len(segment)))
    return segment

def _tts_worker(args):
    idx, start_ms, end_ms, text, voice_id = args
    duration = end_ms - start_ms
    seg = synthesize_tts_for_subtitle(text, duration, voice_id)
    out_path = os.path.join(tempfile.gettempdir(), f"dub_seg_{uuid.uuid4().hex}.wav")
    seg.export(out_path, format="wav")
    return idx, out_path, start_ms, end_ms

def generate_dub_audio(srt_file, output_wav, voice_id, duration_limit_sec=None, target_total_duration_ms=None):
    subtitles = parse_srt_file(srt_file, duration_limit_sec=duration_limit_sec)
    if not subtitles:
        AudioSegment.silent(duration=0).export(output_wav, format="wav")
        return output_wav

    jobs = []
    for idx, (start, end, text) in enumerate(subtitles):
        jobs.append((idx, int(start * 1000), int(end * 1000), text, voice_id))

    max_workers = min(20, max(1, cpu_count()))
    results = [None] * len(jobs)

    # --- Progression: pourcentage unique basé sur le total de sous-titres ---
    total = len(jobs)
    done = 0
    print(f"\rTTS: 0% [0/{total}]", end="", flush=True)

    from concurrent.futures import ProcessPoolExecutor, as_completed
    with ProcessPoolExecutor(max_workers=max_workers) as ex:
        fut_to_idx = {ex.submit(_tts_worker, j): j[0] for j in jobs}
        for fut in as_completed(fut_to_idx):
            idx, path, s_ms, e_ms = fut.result()
            results[idx] = (path, s_ms, e_ms)

            done += 1
            pct = int(done * 100 / total)
            print(f"\rTTS: {pct}% [{done}/{total}]", end="", flush=True)

    print()  # retour à la ligne après 100%
    print("\rExport en cours...")
    dub_audio = AudioSegment.empty()
    current_ms = 0
    try:
        for (start, end, _text), res in zip(subtitles, results):
            start_ms = int(start * 1000) + OFFSET_STR
            end_ms = int(end * 1000) + OFFSET_STR

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
                seg = seg + AudioSegment.silent(duration=(target - len(seg)))

            dub_audio += seg
            current_ms = end_ms
    finally:
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

# =================== Mix & Merge ===================

def mix_audios(audio1_wav, audio2_wav, output_file):
    """
    Mix low_audio + dub -> fichier audio final (codec choisi).
    Utilise la durée la plus longue pour éviter de couper la fin.
    """
    if os.path.getsize(audio1_wav) == 0 or os.path.getsize(audio2_wav) == 0:
        print("Un des fichiers audio est vide. Impossible de mixer.")
        return
    filter_str = (
        f"[0:a]aformat=sample_fmts=s16:channel_layouts=stereo,aresample=async=1,volume={BG_MIX}[first];"
        f"[1:a]aformat=sample_fmts=s16:channel_layouts=stereo,aresample=async=1,volume={TTS_MIX}[second];"
        "[first][second]amix=inputs=2:duration=longest:dropout_transition=0[aout]"
    )
    cmd = [
        "ffmpeg", "-y",
        "-hide_banner", "-loglevel", "error", "-stats",
        "-i", audio1_wav,
        "-i", audio2_wav,
        "-filter_complex", filter_str,
        "-map", "[aout]",
    ] + _final_audio_codec_args() + [
        output_file
    ]
    start = time.perf_counter()
    subprocess.run(cmd, check=True)
    end = time.perf_counter()
    print(end - start)
    return output_file

def encode_original_audio_to_final_codec(original_wav, output_audio):
    """
    Réencode l'audio d'origine (WAV) vers le même codec final pour
    l'ajouter comme deuxième piste audio.
    """
    cmd = [
        "ffmpeg", "-y",
        "-hide_banner", "-loglevel", "error", "-stats",
        "-i", original_wav,
        "-ac", "2",
    ] + _final_audio_codec_args() + [
        output_audio
    ]
    start = time.perf_counter()
    subprocess.run(cmd, check=True)
    end = time.perf_counter()
    print(end - start)
    return output_audio

def merge_to_container(video_fullpath,
                       mixed_audio_file,
                       orig_audio_encoded_file,
                       subtitle_srt_path,
                       output_video_path,
                       orig_audio_name_for_title):
    """
    Fusionne:
      - Vidéo originale (copiée)
      - Piste audio 0: mix TTS (par défaut)  -> title: "<orig> doublé en Français"
      - Piste audio 1: audio original (même codec) -> title: "<orig>"
      - Piste sous-titres: présente mais non par défaut -> title: "Français"
    Pas de -shortest pour garder toute la durée.
    """
    sub_codec = _subtitle_codec_for_container()

    inputs = [
        "-i", video_fullpath,            # 0
        "-i", mixed_audio_file,          # 1
        "-i", orig_audio_encoded_file,   # 2
        "-i", subtitle_srt_path          # 3
    ]

    dub_title = f"{orig_audio_name_for_title} doublé en Français"
    orig_title = orig_audio_name_for_title
    sub_title = "Français"

    cmd = [
        "ffmpeg", "-y",
        "-hide_banner", "-loglevel", "error", "-stats",
    ] + inputs + [
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-map", "2:a:0",
        "-map", "3:0",
        "-c:v", "copy",
        "-c:a:0", "copy",
        "-c:a:1", "copy",
        "-c:s:0", sub_codec,
        "-disposition:a:0", "default",
        "-disposition:a:1", "0",
        "-disposition:s:0", "0",
        "-metadata:s:a:0", f"title={dub_title}",
        "-metadata:s:a:1", f"title={orig_title}",
        "-metadata:s:s:0", f"title={sub_title}",
        output_video_path
    ]
    start = time.perf_counter()
    subprocess.run(cmd, check=True)
    end = time.perf_counter()
    print(end - start)
    return output_video_path


# =================== Extraction ST (MKV -> SRT dans input/) ===================

def extract_first_subtitle_to_srt_into_input(video_fullpath, local_sub_index=0, ocr_lang="fr"):
    """
    Extrait une piste ST du MKV en SRT et l'écrit dans input/ sous le même nom que la vidéo.
    Retourne le chemin du SRT ou None.
    """
    info = _mkvmerge_identify_json(video_fullpath)
    if not info:
        print("MKVToolNix requis pour identifier les pistes (mkvmerge).")
        return None

    sub_tracks = [t for t in info.get("tracks", []) if t.get("type") == "subtitles"]
    if not sub_tracks:
        print("Aucune piste de sous-titres intégrée.")
        return None

    if local_sub_index < 0 or local_sub_index >= len(sub_tracks):
        local_sub_index = 0
    t_sel = sub_tracks[local_sub_index]
    track_id = t_sel.get("id")
    codec_id = (t_sel.get("properties", {}).get("codec_id") or "").lower()

    base = os.path.splitext(os.path.basename(video_fullpath))[0]
    target_srt = _join_input(base + ".srt")

    is_text = codec_id.startswith("s_text/")
    if is_text:
        try:
            cmd = [
                "ffmpeg", "-y",
                "-hide_banner", "-loglevel", "error", "-stats",
                "-i", video_fullpath,
                "-map", f"0:s:{local_sub_index}",
                "-c:s", "subrip",
                target_srt
            ]
            start = time.perf_counter()
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            end = time.perf_counter()
            print(end - start)
            if os.path.exists(target_srt) and os.path.getsize(target_srt) > 0:
                strip_subtitle_tags_inplace(target_srt)
                print(f"SRT extrait (texte) -> {target_srt}")
                return target_srt
            print("Échec extraction SRT (texte).")
        except subprocess.CalledProcessError as e:
            print("Erreur ffmpeg extraction ST texte:", (e.stderr or "")[-400:])
        return None

    mkvextract = _find_exe([
        "mkvextract",
        r"C:\Program Files\MKVToolNix\mkvextract.exe",
        r"C:\Program Files (x86)\MKVToolNix\mkvextract.exe",
    ])
    if not mkvextract:
        print("mkvextract introuvable.")
        return None

    tmp_dir = tempfile.mkdtemp(prefix="subs_")
    try:
        ext = ".sup" if "pgs" in codec_id or "hdmv/pgs" in codec_id else ".sub"
        base_noext = os.path.join(tmp_dir, base)
        ocr_input = base_noext + ext
        cmd = [mkvextract, "tracks", video_fullpath, f"{track_id}:{ocr_input}"]
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        se = _find_exe([
            "SubtitleEdit",
            "SubtitleEdit.exe",
            r"C:\Program Files\Subtitle Edit\SubtitleEdit.exe",
            r"C:\Program Files (x86)\Subtitle Edit\SubtitleEdit.exe",
        ])
        if se:
            tmp_out = os.path.join(tmp_dir, base + ".srt")
            cmd = [
                se, "/convert", ocr_input, "subrip",
                f"/outputfilename:{tmp_out}",
                "/encoding:utf-8",
                "/ocrengine:tesseract",
                "/overwrite"
            ]
            # subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=tmp_dir)
            subprocess.run(cmd, check=True, cwd=tmp_dir)
            if os.path.exists(tmp_out) and os.path.getsize(tmp_out) > 0:
                os.replace(tmp_out, target_srt)
                strip_subtitle_tags_inplace(target_srt)
                print(f"SRT OCR (Subtitle Edit) -> {target_srt}")
                return target_srt
            else:
                print("Subtitle Edit n’a pas produit de .srt.")

        if ext == ".sub":
            vobsub2srt = _find_exe(["vobsub2srt", "vobsub2srt.exe"])
            if vobsub2srt:
                cmd = [vobsub2srt, "--lang", ocr_lang, base_noext]
                subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=tmp_dir)
                produced = base_noext + ".srt"
                if os.path.exists(produced) and os.path.getsize(produced) > 0:
                    os.replace(produced, target_srt)
                    strip_subtitle_tags_inplace(target_srt)
                    print(f"SRT OCR (vobsub2srt) -> {target_srt}")
                    return target_srt
                else:
                    print("vobsub2srt n’a pas produit de .srt.")

        print("Aucun OCR disponible.")
        return None
    finally:
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass


# =================== Pipeline ===================

def _resolve_srt_for_video(video_fullpath, sub_choice_global):
    """
    Détermine le SRT à utiliser pour une vidéo donnée en mode AUTO.
    - si sub_choice_global == ("srt", path): on attend un sidecar SRT pour CHAQUE vidéo
      (identique = l'utilisateur a vérifié).
    - si sub_choice_global == ("mkv", idx): on extrait systématiquement cette piste vers input/.
    """
    kind, value = sub_choice_global
    if kind == "srt":
        srt_path = find_sidecar_srt(video_fullpath)
        if srt_path:
            strip_subtitle_tags_inplace(srt_path)
            return srt_path
        else:
            print(f"[AUTO] SRT manquant pour {video_fullpath}.")
            return None
    else:
        # Extraction à partir de la piste MKV (index local 'value')
        srt_path = extract_first_subtitle_to_srt_into_input(video_fullpath, local_sub_index=value)
        return srt_path

def process_one_video(video_name,
                      voice_id,
                      audio_ffmpeg_index=None,
                      sub_choice=None,
                      orig_audio_name=None,
                      limit_duration_sec=None,
                      test_prefix=""):
    """
    video_name est le nom de fichier situé dans input/.
    Si audio_ffmpeg_index / sub_choice / orig_audio_name sont fournis -> aucun prompt.
    Sinon, on interroge (mode manuel).
    """
    video_fullpath = _join_input(video_name)
    base, _ext = os.path.splitext(video_name)

    # AUDIO INDEX
    if audio_ffmpeg_index is None:
        audio_ffmpeg_index = choose_audio_track_ffmpeg_index(video_fullpath)

    # SOURCE ST
    if sub_choice is None:
        chosen = choose_subtitle_source(video_fullpath)
        if chosen is None:
            print(f"Aucun sous-titre pour {video_name}. Création d'un raccourci vers la source.")
            return shortcut_name
        # En mode manuel, on concrétise en srt_path maintenant
        if chosen[0] == "srt":
            srt_path = chosen[1]
        else:
            srt_path = extract_first_subtitle_to_srt_into_input(video_fullpath, local_sub_index=chosen[1])
            if not srt_path:
                print(f"Impossible d'obtenir un SRT pour {video_name}.")
                return
    else:
        # Mode AUTO : on résout via la règle globale
        srt_path = _resolve_srt_for_video(video_fullpath, sub_choice)
        if not srt_path:
            print(f"[AUTO] Abandon de {video_name} (pas de SRT utilisable).")
            return

    # Nettoyage SRT (au cas où)
    strip_subtitle_tags_inplace(srt_path)

    # NOM PISTE ORIG
    if orig_audio_name is None:
        orig_audio_name = ask_str("\nNom de la piste audio d'origine (ex. Japonais)", "Original")

    # Fichiers intermédiaires (WAV)
    orig_wav = _join_output(f"{test_prefix}{base}_orig.wav")
    print("\nExtraction de l'audio d'origine (WAV PCM)...")
    extract_audio_track(video_fullpath, audio_ffmpeg_index, orig_wav, duration_sec=limit_duration_sec)

    # Durée cible pour le TTS (évite de couper la fin)
    orig_len_ms = len(AudioSegment.from_file(orig_wav))

    subtitles = parse_srt_file(srt_path, duration_limit_sec=limit_duration_sec)

    lowered_wav = _join_output(f"{test_prefix}{base}_lowered.wav")
    print("\nDucking des passages sous-titrés -> WAV...")
    lower_audio_during_subtitles(orig_wav, subtitles, lowered_wav, reduction_db=DB_REDUCT, fade_duration=100)

    dub_wav = _join_output(f"{test_prefix}{base}_dub.wav")
    print("\nGénération TTS -> WAV...")
    generate_dub_audio(
        srt_path,
        dub_wav,
        voice_id,
        duration_limit_sec=limit_duration_sec,
        target_total_duration_ms=orig_len_ms
    )

    mixed_ext = _final_audio_ext()
    mixed_audio = _join_output(f"{test_prefix}{base}_mixed{mixed_ext}")
    print(f"\nMixage BG+TTS -> {AUDIO_CODEC_FINAL.upper()} ...")
    mix_audios(lowered_wav, dub_wav, mixed_audio)

    # Encoder l'audio original au même codec (deviendra piste audio #2)
    orig_encoded = _join_output(f"{test_prefix}{base}_orig{mixed_ext}")
    print("\nRéencodage de la piste originale au codec final...")
    encode_original_audio_to_final_codec(orig_wav, orig_encoded)

    final_ext = _final_video_ext()
    final_video = _join_output(f"{test_prefix}dub_{base}{final_ext}")
    print("\nFusion finale (vidéo + 2 audios + ST non par défaut)...")
    merge_to_container(
        video_fullpath,
        mixed_audio,
        orig_encoded,
        srt_path,
        final_video,
        orig_audio_name_for_title=orig_audio_name
    )
    print(f"\nFichier final : {final_video}")

    # Nettoyage intermédiaires
    for f in [orig_wav, lowered_wav, dub_wav, mixed_audio, orig_encoded]:
        try:
            if os.path.exists(f):
                os.remove(f)
        except Exception as e:
            print(f"Suppression échouée ({f}): {e}")

    return final_video


# =================== MAIN ===================

def main():
    global BG_MIX, TTS_MIX, DB_REDUCT, OFFSET_STR

    candidate_files = list_input_videos()
    selected_files = choose_files(candidate_files)
    if not selected_files:
        print("Aucun fichier sélectionné.")
        sys.exit(1)

    mode = ask_mode()

    # Détection voix FR
    engine = pyttsx3.init()
    voices = engine.getProperty("voices")
    french_voice_id_default = None
    for voice in voices:
        if "fr" in str(voice.languages).lower() or "french" in voice.name.lower():
            french_voice_id_default = voice.id
            break
    if not french_voice_id_default and voices:
        print("Aucune voix FR trouvée, utilisation de la voix par défaut.")
        french_voice_id_default = voices[0].id
    engine.stop()

    if mode == "auto":
        # Réglages communs (une seule fois)
        DB_REDUCT = ask_float("\nRéduction de volume (ducking) en dB", DB_REDUCT)
        OFFSET_STR = ask_int("\nDécalage ST/TTS en ms (négatif = plus tôt)", OFFSET_STR)
        BG_MIX = ask_float("\nNiveau BG (1.0 inchangé)", BG_MIX)
        TTS_MIX = ask_float("\nNiveau TTS (1.0 inchangé)", TTS_MIX)

        # Sélection unique sur la première vidéo : piste audio + source sous-titres + nom piste
        first_video = selected_files[0]
        first_full = _join_input(first_video)
        print(f"\n[AUTO] Configuration sur la première vidéo : {first_video}")

        audio_ffmpeg_index_global = choose_audio_track_ffmpeg_index(first_full)
        sub_choice_global = choose_subtitle_source(first_full)
        if sub_choice_global is None:
            print("[AUTO] Pas de sous-titre détecté sur la première vidéo. Arrêt.")
            sys.exit(1)
        orig_audio_name_global = ask_str("\nNom de la piste audio d'origine (ex. Japonais)", "Original")

        print(f"\n[AUTO] Configuration verrouillée. Traitement de {len(selected_files)} vidéo(s) sans autre question.")
        for video_name in selected_files:
            process_one_video(
                video_name,
                french_voice_id_default,
                audio_ffmpeg_index=audio_ffmpeg_index_global,
                sub_choice=sub_choice_global,
                orig_audio_name=orig_audio_name_global
            )

    else:
        for video_name in selected_files:
            print(f"\n===== Vidéo : {video_name} =====")
            local_db = DB_REDUCT
            local_off = OFFSET_STR
            local_bg = BG_MIX
            local_tts = TTS_MIX

            while True:
                print("(Entrée pour conserver la valeur entre crochets)")
                local_db = ask_float("Réduction de volume (dB)", local_db)
                local_off = ask_int("Décalage ST/TTS (ms)", local_off)
                local_bg = ask_float("Niveau BG (1.0 inchangé)", local_bg)
                local_tts = ask_float("Niveau TTS (1.0 inchangé)", local_tts)

                DB_REDUCT = local_db
                OFFSET_STR = local_off
                BG_MIX = local_bg
                TTS_MIX = local_tts

                want_test = ask_yes_no("Faire un test 5 minutes ?", default_no=True)
                if want_test:
                    test_out = process_one_video(
                        video_name,
                        french_voice_id_default,
                        limit_duration_sec=300,
                        test_prefix="TEST_"
                    )
                    print("\nTest terminé. Ouvre la vidéo générée et vérifie.")
                    ok = ask_yes_no("OK ? Générer la version complète ?", default_no=False)
                    try:
                        if test_out and os.path.exists(test_out):
                            os.remove(test_out)
                            print(f"Vidéo test supprimée : {test_out}")
                    except Exception as e:
                        print(f"Suppression vidéo test échouée ({e})")

                    if ok:
                        process_one_video(video_name, french_voice_id_default)
                        break
                    else:
                        print("On refait un test avec d'autres options.")
                        continue
                else:
                    process_one_video(video_name, french_voice_id_default)
                    break

    print("\nTerminé.")


if __name__ == "__main__":
    main()
