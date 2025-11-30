# add_dub — Subtitle Vocalization & Automated Voice-Over for Windows

**add_dub** is a powerful tool that automatically transforms video subtitles into **spoken voice (TTS)** and creates a **new video with audio voice-over**.
Its primary goal is to make content accessible to those who have difficulty reading subtitles—whether due to **visual fatigue**, **visual impairment**, or simply preference—by allowing them to **listen** instead.

With the new **Translation Feature**, you can now vocalize videos in your native language, even if the original subtitles are in a foreign language!

## 🚀 Features

-   **Subtitle Vocalization**: Converts SRT subtitles into synchronized audio voice-over.
-   **AI Translation**: Automatically translates subtitles before vocalization (supports 100+ languages via EasyNMT).
-   **Multiple TTS Engines**:
    -   **OneCore (Windows)**: Fast, offline, uses installed system voices.
    -   **Edge TTS**: High-quality, natural-sounding voices (requires Internet).
    -   **gTTS**: Simple, lightweight (requires Internet).
-   **Smart Mixing**: Automatically "ducks" (lowers) the original audio volume when the TTS speaks.
-   **Batch Processing**: Process entire folders of videos recursively.
-   **Portable**: No complex installation required.

## 📥 Input & Output

-   **Input**: A video file (MKV, MP4, AVI, etc.) with embedded subtitles or an external `.srt` file.
-   **Output**: An **MKV** video file containing:
    -   **Track 0**: Original Video
    -   **Track 1**: Mixed Audio (TTS + Original Background)
    -   **Track 2**: Original Audio (Isolated)
    -   **Track 3**: Subtitles

---

## 📦 Installation

### Option 1: Portable Version (Recommended)
Download the latest release, unzip it, and you're ready to go!
[📥 Download add_dub_win64.zip](https://github.com/Jobijoba2000/add_dub/releases)

### Option 2: From Source
If you prefer to run from source:
```bash
git clone https://github.com/Jobijoba2000/add_dub.git
cd add_dub
start_add_dub.bat
```

---

## 🎮 Usage

### First Launch
Simply run:
```cmd
start_add_dub.bat
```
On the first run, the script will:
1.  Download/Install the **Toolbox** (Portable Python, FFmpeg, MKVToolNix, etc.).
2.  Create necessary directories: `input`, `output`, `tmp`, `srt`.
3.  Generate a default `options.conf`.

### Interactive Mode
Just run `start_add_dub.bat` without arguments. The tool will guide you through:
1.  **Selecting Videos**: Choose from the `input/` folder.
2.  **Audio Track**: Select the source audio track.
3.  **Subtitles**: Choose embedded or external subtitles.
4.  **TTS Engine**: Select OneCore, Edge TTS, or gTTS.
5.  **Translation**: Optionally translate subtitles to your preferred language (e.g., `fr`, `en`, `es`, `ar`, `zh`...).
6.  **Configuration**: Adjust volume, speed, and offsets.

### Batch Mode (CLI)
For automated processing, use the `--batch` flag.

**Examples:**

*   **Process a single file:**
    ```cmd
    start_add_dub.bat --batch -i "C:\Videos\movie.mkv" --tts-engine edge --voice "en-US-AriaNeural"
    ```

*   **Process a folder recursively:**
    ```cmd
    start_add_dub.bat --batch -i "C:\Videos\Series" --recursive
    ```

*   **Translate and Dub (e.g., English to French):**
    ```cmd
    start_add_dub.bat --batch -i "C:\Videos\movie.mkv" --translate --translate-to fr --voice "fr-FR-DeniseNeural"
    ```

*   **Custom Mix Settings:**
    ```cmd
    start_add_dub.bat --batch -i "C:\Videos\movie.mkv" --bg-mix 0.8 --tts-mix 1.2 --ducking-db -5.0
    ```

---

## ⚙️ Configuration (`options.conf`)

The `options.conf` file allows you to set default values.
Format: `key = value` or `key = value d` (add `d` to ask the user at runtime).

**Key Options:**
-   `tts_engine`: `onecore`, `edge`, `gtts`.
-   `voice_id`: Specific voice ID (use `--list-voices` to find them).
-   `translate`: `true` or `false` (enable translation by default).
-   `translate_to`: Target language code (e.g., `fr`, `en`).
-   `min_rate_tts` / `max_rate_tts`: Speed limits for TTS.
-   `ducking`: Volume reduction of background audio in dB (e.g., `-5.0`).

---

## 🌍 Supported Languages

**UI Languages**:
The interface automatically detects your system language. Supported languages include:
-   English (`en`)
-   French (`fr`)
-   Spanish (`es`)
-   Italian (`it`)
-   German (`de`)
-   Portuguese (`pt`)
-   Russian (`ru`)
-   Greek (`el`)
-   Chinese (`zh`)
-   Arabic (`ar`)
-   Korean (`ko`)
-   Japanese (`ja`)

**Translation Support**:
You can translate subtitles **from** and **to** almost any language supported by EasyNMT/HuggingFace models.

---

## 🛠️ Troubleshooting

-   **"ffmpeg not found"**: Ensure the initial setup completed successfully. The `tools` folder should contain ffmpeg.
-   **TTS fails**: Check your internet connection if using Edge TTS or gTTS. For OneCore, ensure the voice is installed in Windows settings.
-   **Translation errors**: The first translation might be slow as it downloads models. Ensure you have a stable internet connection.

---

## 📄 License

This project is licensed under the **MIT License**.
Dependencies included in the Toolbox are subject to their respective licenses.
