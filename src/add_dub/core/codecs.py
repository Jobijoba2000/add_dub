# src/add_dub/core/codecs.py

def final_audio_ext(audio_codec_final: str) -> str:
    codec = (audio_codec_final or "").lower()
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

def video_ext(audio_codec_final: str) -> str:
    # MP4 si AAC (pour compatibilité), sinon MKV
    return ".mp4" if (audio_codec_final or "").lower() == "aac" else ".mkv"

def subtitle_codec_for_container(audio_codec_final: str) -> str:
    # MP4 ne supporte pas SRT -> mov_text ; MKV -> srt
    return "mov_text" if video_ext(audio_codec_final) == ".mp4" else "srt"

def final_audio_codec_args(audio_codec_final: str, audio_bitrate: str | None) -> list[str]:
    codec = (audio_codec_final or "").lower()
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

    if audio_bitrate and codec in lossy:
        args += ["-b:a", audio_bitrate]
    return args
