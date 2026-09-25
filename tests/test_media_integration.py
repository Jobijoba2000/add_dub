"""Vrais petits médias FFmpeg : canaux, gains, codecs, atomicité et pipeline."""
from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
import wave
import numpy as np
from add_dub.io import fs
from add_dub.core.options import DubOptions
from add_dub.core.services import Services
from add_dub.adapters.ffmpeg import dub_in_one_pass, probe_media, extract_audio_track, run_ffmpeg_with_percentage


def write_wav(path, value, channels=2, rate=48000, seconds=2):
    with wave.open(str(path), 'wb') as stream:
        stream.setparams((channels, 2, rate, 0, 'NONE', 'not compressed'))
        stream.writeframes(np.full((rate * seconds, channels), value, dtype='<i2').tobytes())


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg local nécessaire')
class MediaIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='dub-media-tests-')
        cls.root = Path(cls.temporary.name)
        cls.original = cls.root / 'original.wav'
        cls.bg = cls.root / 'bg.wav'
        cls.tts = cls.root / 'tts.wav'
        cls.srt = cls.root / 'source.srt'
        cls.video = cls.root / 'source.mkv'
        write_wav(cls.original, 1000, channels=6)
        write_wav(cls.bg, 1000)
        write_wav(cls.tts, 0)
        cls.srt.write_text('1\n00:00:00,100 --> 00:00:01,500\nBonjour\n', encoding='utf-8')
        subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-f', 'lavfi', '-i',
                        'color=c=blue:size=64x64:rate=10:duration=2', '-i', str(cls.original),
                        '-i', str(cls.srt), '-map', '0:v', '-map', '1:a', '-map', '2:s',
                        '-c:v', 'mpeg4', '-c:a', 'pcm_s16le', '-c:s', 'srt', str(cls.video)],
                       check=True, capture_output=True, timeout=30)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def mux(self, name, opts=None, **kwargs):
        output = self.root / name
        dub_in_one_pass(video_fullpath=str(self.video), bg_wav=str(self.bg), tts_wav=str(self.tts),
                        original_wav=str(self.original), subtitle_srt_path=str(self.srt),
                        output_video_path=str(output), opts=opts or DubOptions(audio_ffmpeg_index=1, audio_codec='pcm_s16le'),
                        **kwargs)
        return output

    def decode(self, path, track):
        return subprocess.check_output(['ffmpeg', '-v', 'error', '-nostdin', '-i', str(path),
                                        '-map', f'0:a:{track}', '-f', 's16le', '-c:a', 'pcm_s16le', '-'], timeout=30)

    def test_original_multichannel_audio_is_bit_exact(self):
        output = self.mux('preserved.mkv')
        streams = probe_media(output)['streams']
        audio = [stream for stream in streams if stream['codec_type'] == 'audio']
        self.assertEqual([stream['channels'] for stream in audio], [2, 6])
        self.assertEqual(self.decode(output, 1), self.decode(self.video, 0))
        # Silence TTS must not halve the background's gain.
        mixed = np.frombuffer(self.decode(output, 0), dtype='<i2')
        self.assertGreater(np.median(np.abs(mixed[10000:-10000])), 950)

    def test_all_advertised_audio_codecs_produce_valid_outputs(self):
        for codec in ('ac3', 'aac', 'mp3', 'libopus', 'opus', 'flac', 'libvorbis', 'vorbis', 'pcm_s16le'):
            with self.subTest(codec=codec):
                output = self.mux(f'codec-{codec}.mkv', DubOptions(audio_ffmpeg_index=1, audio_codec=codec))
                self.assertGreater(float(probe_media(output)['format']['duration']), 1.9)

    def test_duration_limit_applies_to_video_too(self):
        output = self.mux('excerpt.mkv', duration_sec=1)
        self.assertLessEqual(float(probe_media(output)['format']['duration']), 1.6)

    def test_ffmpeg_error_contains_diagnostic(self):
        with self.assertRaisesRegex(RuntimeError, 'not_a_real_filter'):
            run_ffmpeg_with_percentage(['ffmpeg', '-v', 'error', '-i', str(self.video),
                                        '-af', 'not_a_real_filter', '-f', 'null', '-'], str(self.video))

    def test_full_pipeline_preserves_inputs_and_cleans_work(self):
        from add_dub.core.pipeline import process_one_video
        from add_dub.core.subtitles import resolve_srt_for_video
        work = self.root / 'work'
        work.mkdir(exist_ok=True)
        original_subs = self.srt.read_bytes()
        def synth(**kwargs):
            write_wav(kwargs['output_wav'], 200)
        services = Services(resolve_srt_for_video=resolve_srt_for_video, generate_dub_audio=synth,
                            choose_files=lambda items: items, choose_audio_track=lambda _: 1,
                            choose_subtitle_source=lambda _: ('srt', str(self.srt)), ui=Mock())
        options = DubOptions(audio_ffmpeg_index=1, sub_choice=('srt', str(self.srt)),
                             audio_codec='pcm_s16le', voice_id='fr', batch_mode=True)
        with patch.object(fs, 'TMP_DIR', str(work)), patch('add_dub.core.pipeline.list_available_voices', return_value=[]):
            result = process_one_video(input_video_path=str(self.video), input_video_name=self.video.name,
                                       output_dir_path=str(self.root / 'pipeline'), opts=options, svcs=services)
            self.assertTrue(Path(result).is_file())
            self.assertEqual(list(work.iterdir()), [])
            self.assertEqual(self.srt.read_bytes(), original_subs)
            with self.assertRaises(FileExistsError):
                process_one_video(input_video_path=str(self.video), input_video_name=self.video.name,
                                  output_dir_path=str(self.root / 'pipeline'), opts=options, svcs=services)
            self.assertEqual(list(work.iterdir()), [])

    def test_real_spawned_tts_workers_complete_without_network(self):
        from add_dub.core.tts_generate import generate_dub_audio
        from add_dub.io.work import work_directory
        cues = self.root / 'silence.srt'
        cues.write_text('1\n00:00:00,000 --> 00:00:00,500\n...\n', encoding='utf-8')
        with work_directory(self.root):
            output = self.root / 'silent-tts.wav'
            generate_dub_audio(str(cues), str(output), DubOptions(tts_engine='edge'), target_total_duration_ms=1000)
        with wave.open(str(output)) as audio:
            self.assertAlmostEqual(audio.getnframes() / audio.getframerate(), 1)
