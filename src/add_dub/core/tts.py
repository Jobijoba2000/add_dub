# src/add_dub/core/tts.py
import os
import tempfile
import uuid
import pyttsx3
from pydub import AudioSegment

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
