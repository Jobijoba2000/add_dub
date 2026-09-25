"""Régressions de l'audit : données synthétiques, aucun service distant."""
import io
import json
import multiprocessing
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import wave
import numpy as np

from add_dub.io import fs
from add_dub.io.work import work_directory, publish
from add_dub.core import subtitles, translation
from add_dub.core.options import DubOptions


def srt(text='été français'):
    return f'1\n00:00:00,000 --> 00:00:01,000\n{text}\n'


def wav(path, value=1000, frames=8000, channels=1):
    with wave.open(str(path), 'wb') as output:
        output.setparams((channels, 2, 8000, 0, 'NONE', 'not compressed'))
        output.writeframes(np.full((frames, channels), value, dtype='<i2').tobytes())


class SubtitleSafetyTests(unittest.TestCase):
    def test_encodings_survive_cleaning(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'cue.srt'
            for encoding in ('utf-8', 'utf-8-sig', 'cp1252', 'utf-16'):
                with self.subTest(encoding=encoding):
                    path.write_bytes(srt('<i>été français</i>').encode(encoding))
                    subtitles.strip_subtitle_tags_inplace(str(path))
                    self.assertEqual(subtitles.parse_srt_file(str(path)), [(0, 1, 'été français')])

    def test_homonyms_keep_own_sidecars_and_central_source_is_unchanged(self):
        with tempfile.TemporaryDirectory() as root, work_directory(root), patch.object(fs, 'SRT_DIR', root):
            root = Path(root)
            central = root / 'episode.srt'
            central.write_text(srt('<i>central</i>'), encoding='utf-8')
            for name in ('first', 'second'):
                folder = root / name
                folder.mkdir()
                video = folder / 'episode.mp4'
                video.touch()
                sidecar = video.with_suffix('.srt')
                original = srt(f'<b>{name}</b>').encode('cp1252')
                sidecar.write_bytes(original)
                result = subtitles.resolve_srt_for_video(str(video), ('srt', None))
                self.assertEqual(subtitles.parse_srt_file(result)[0][2], name)
                self.assertEqual(sidecar.read_bytes(), original)
            result = subtitles.resolve_srt_for_video(str(root / 'episode.mp4'), ('srt', str(central)))
            self.assertNotEqual(result, str(central))
            self.assertIn('<i>', central.read_text(encoding='utf-8'))

    def test_work_is_cleaned_after_exception_and_context_restored(self):
        with tempfile.TemporaryDirectory() as root:
            before = fs.get_tmp_dir()
            with self.assertRaises(RuntimeError):
                with work_directory(root) as directory:
                    Path(fs.join_tmp('owned')).touch()
                    raise RuntimeError('failed')
            self.assertFalse(Path(directory).exists())
            self.assertEqual(fs.get_tmp_dir(), before)

    def test_translation_cache_tracks_content_and_identity(self):
        with tempfile.TemporaryDirectory() as root, patch.object(fs, 'SRT_DIR', root):
            path = Path(root) / 'input.srt'
            opts = DubOptions(translate=True, translate_from='en', translate_to='fr')
            with patch.object(translation, 'translate_subtitles', side_effect=lambda cues, *a, **k: cues) as translate:
                path.write_text(srt('one'), encoding='utf-8')
                first, _ = translation.translate_file(str(path), 'A/episode.mp4', ('srt', None), opts, None)
                again, _ = translation.translate_file(str(path), 'A/episode.mp4', ('srt', None), opts, None)
                self.assertEqual(first, again)
                self.assertEqual(translate.call_count, 1)
                second, _ = translation.translate_file(str(path), 'B/episode.mp4', ('srt', None), opts, None)
                path.write_text(srt('two'), encoding='utf-8')
                changed, _ = translation.translate_file(str(path), 'A/episode.mp4', ('srt', None), opts, None)
                self.assertEqual(len({first, second, changed}), 3)


class TranslationSafetyTests(unittest.TestCase):
    def test_missing_local_models_never_upload_text(self):
        with patch.object(translation, '_translate_with_opus_pair', return_value=None), \
             patch.object(translation, '_translate_with_nllb', return_value=None), \
             patch.object(translation, '_translate_with_google') as online:
            with self.assertRaises(RuntimeError):
                translation.translate_subtitles([(0, 1, 'Hello')], 'fr', source_lang='en', engine='ctranslate2')
            online.assert_not_called()

    def test_google_delimiter_loss_retries_individual_cues(self):
        with patch('add_dub.adapters.http.google_translator') as factory:
            factory.return_value.translate.side_effect = ['Bonjour. Au revoir.', 'Bonjour.', 'Au revoir.']
            result = translation._translate_with_google(['Hello.', 'Goodbye.'], 'en', 'fr')
            self.assertEqual(result, ['Bonjour.', 'Au revoir.'])

    def test_failed_local_packet_is_an_error(self):
        translator, source, target = Mock(), Mock(), Mock()
        source.encode.return_value = ['Hello']
        translator.translate_batch.side_effect = RuntimeError('model failure')
        with patch.object(translation, '_get_opus_translator_and_tokenizer', return_value=(translator, source, target, 'model')):
            with self.assertRaises(RuntimeError):
                translation._translate_with_opus_pair(['Hello'], 'en', 'fr')

    def test_offline_missing_models_do_not_download(self):
        token = translation.OFFLINE.set(True)
        try:
            with patch('huggingface_hub.snapshot_download') as download, \
                 patch.object(translation.os.path, 'exists', return_value=False), \
                 patch.object(translation, '_NLLB_CACHE', None):
                self.assertIsNone(translation._get_nllb_translator_and_tokenizer())
                download.assert_not_called()
        finally:
            translation.OFFLINE.reset(token)


class NetworkContractTests(unittest.TestCase):
    def test_gtts_uses_verified_bounded_transport(self):
        import requests
        from add_dub.adapters.http import google_speech, TIMEOUT
        response = Mock()
        response.iter_lines.return_value = [b'jQ1olc","[\\"YWJj\\"]"']
        with patch.object(requests.Session, 'send', return_value=response) as send:
            try:
                list(google_speech(text='Bonjour', lang='fr', tld='com', slow=False).stream())
            except Exception:
                pass  # Réponse synthétique ; le contrat audité est celui du transport.
        self.assertTrue(send.called)
        self.assertIs(send.call_args.kwargs['verify'], True)
        self.assertEqual(send.call_args.kwargs['timeout'], TIMEOUT)

    def test_google_requests_are_bounded_and_tls_verified(self):
        import requests
        from add_dub.adapters.http import google_translator, TIMEOUT
        response = Mock(status_code=200, text='<div class="t0">Bonjour</div>')
        with patch.object(requests.Session, 'send', return_value=response) as send:
            self.assertEqual(google_translator(source='en', target='fr').translate('Hello'), 'Bonjour')
        self.assertEqual(send.call_args.kwargs['timeout'], TIMEOUT)
        self.assertIs(send.call_args.kwargs['verify'], True)


class AudioReliabilityTests(unittest.TestCase):
    def test_overlapping_cues_sum_deterministically_and_clip(self):
        from add_dub.core.tts_generate import assemble_segments
        with tempfile.TemporaryDirectory() as root, work_directory(root):
            root = Path(root)
            wav(root / 'a.wav', 20000)
            wav(root / 'b.wav', 20000)
            cues = [(0, 1, 'a'), (.5, 1.5, 'b')]
            results = [(0, str(root / 'a.wav'), 0, 1000), (1, str(root / 'b.wav'), 500, 1500)]
            assemble_segments(cues, results, root / 'out.wav', 2000)
            with wave.open(str(root / 'out.wav')) as stream:
                values = np.frombuffer(stream.readframes(stream.getnframes()), dtype='<i2')
            self.assertTrue(np.all(values[:4000] == 20000))
            self.assertTrue(np.all(values[4000:8000] == 32767))
            self.assertTrue(np.all(values[8000:12000] == 20000))
            self.assertTrue(np.all(values[12000:] == 0))

    def test_ducking_across_block_boundary_preserves_outside_samples(self):
        from add_dub.core.ducking import lower_audio_during_subtitles
        with tempfile.TemporaryDirectory() as root:
            source, output = Path(root) / 'in.wav', Path(root) / 'out.wav'
            wav(source, 10000, frames=80000)
            lower_audio_during_subtitles(source, [(8, 9, 'voice')], output, reduction_db=-6, fade_duration=0)
            with wave.open(str(output)) as stream:
                values = np.frombuffer(stream.readframes(stream.getnframes()), dtype='<i2')
            self.assertEqual(len(values), 80000)
            self.assertTrue(np.all(values[:64000] == 10000))
            self.assertTrue(np.all(values[64000:72000] == 5012))
            self.assertTrue(np.all(values[72000:] == 10000))

    def test_timeout_terminates_pool_without_replaying_jobs(self):
        from add_dub.core.tts_generate import synthesize_jobs
        pool = Mock()
        pool.imap_unordered.return_value.next.side_effect = multiprocessing.TimeoutError
        with patch('add_dub.core.tts_generate.multiprocessing.get_context') as context:
            context.return_value.Pool.return_value = pool
            with self.assertRaises(TimeoutError):
                synthesize_jobs([('job',)])
        pool.imap_unordered.assert_called_once()
        pool.terminate.assert_called_once()
        pool.join.assert_called_once()

    def test_edge_failure_is_not_silence(self):
        from add_dub.core.tts_edge import synthesize_tts_for_subtitle
        with patch('add_dub.core.tts_edge._synthesize', side_effect=RuntimeError('offline')):
            with self.assertRaises(RuntimeError):
                synthesize_tts_for_subtitle('Bonjour', 1000, 'fr-FR-HenriNeural', DubOptions())

    def test_gtts_failure_is_not_silence(self):
        from add_dub.core.tts_gtts import synthesize_tts_for_subtitle
        with patch('add_dub.core.tts_gtts._synthesize', side_effect=RuntimeError('offline')):
            with self.assertRaises(RuntimeError):
                synthesize_tts_for_subtitle('Bonjour', 1000, 'fr', DubOptions())

    def test_mpv_loading_state_is_not_playing_or_seekable(self):
        from add_dub.adapters.mpv import Player
        player = Player.__new__(Player)
        player.loaded = False
        player.error = None
        player._drain_events = Mock()
        player._get = Mock(return_value='no')
        player._command = Mock()
        self.assertFalse(player.is_playing())
        self.assertFalse(player.set_position(.5))
        player._command.assert_not_called()

    def test_ducking_zero_gain_preserves_pcm_bytes(self):
        from add_dub.core.ducking import lower_audio_during_subtitles
        with tempfile.TemporaryDirectory() as root:
            source, target = Path(root) / 'in.wav', Path(root) / 'out.wav'
            wav(source, value=-20000, channels=2)
            lower_audio_during_subtitles(source, [(0, 1, 'voice')], target, reduction_db=0)
            self.assertEqual(source.read_bytes(), target.read_bytes())


class OutputSafetyTests(unittest.TestCase):
    def test_publish_does_not_overwrite_by_default(self):
        with tempfile.TemporaryDirectory() as root:
            source, target = Path(root) / 'new', Path(root) / 'old'
            source.write_text('new')
            target.write_text('old')
            with self.assertRaises(FileExistsError):
                publish(source, target)
            self.assertEqual(target.read_text(), 'old')
            publish(source, target, overwrite=True)
            self.assertEqual(target.read_text(), 'new')

    def test_failed_mux_preserves_existing_video_and_removes_partial(self):
        from add_dub.adapters.ffmpeg import dub_in_one_pass
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / 'film.mkv'
            target.write_bytes(b'previous')
            def fail(**kwargs):
                Path(kwargs['output_video_path']).write_bytes(b'truncated')
                raise RuntimeError('disk full')
            with patch('add_dub.adapters.ffmpeg._dub_in_one_pass', side_effect=fail):
                with self.assertRaises(RuntimeError):
                    dub_in_one_pass(output_video_path=str(target), opts=DubOptions(overwrite=True))
            self.assertEqual(target.read_bytes(), b'previous')
            self.assertEqual(list(Path(root).iterdir()), [target])

    def test_invalid_existing_output_is_not_skipped_by_gui(self):
        from add_dub.gui.run import partition_existing
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / 'film [dub-fr].mkv').touch()
            entry = (0, SimpleNamespace(path='film.mkv'), ['--skip-existing', '--voice', 'fr', '--output-dir', root])
            with patch('add_dub.adapters.ffmpeg.validate_media', side_effect=ValueError('invalid')):
                self.assertEqual(partition_existing([entry]), ([entry], []))

    def test_interrupted_ocr_download_never_installs_partial(self):
        from add_dub.adapters.downloads import resource
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'fra.traineddata'
            response = Mock()
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
            response.read.side_effect = [b'partial', OSError('disconnected')]
            with patch('urllib.request.urlopen', return_value=response):
                with self.assertRaises(OSError):
                    resource('https://example.invalid/resource', path)
            self.assertEqual(list(Path(root).iterdir()), [])

    def test_player_audio_failure_does_not_publish_voice(self):
        from add_dub.player.core.generation import main
        from add_dub.player.io import fs as player_fs
        with tempfile.TemporaryDirectory() as root, patch.object(player_fs, 'TMP_DIR', root), \
             patch.object(player_fs, 'ensure_base_dirs'), patch.object(fs, 'TMP_DIR', root), \
             patch.object(fs, 'SRT_DIR', root):
            root = Path(root)
            path = root / 'cue.srt'
            path.write_text(srt(), encoding='utf-8')
            request = {'video': 'film.mkv', 'ordinal': 0, 'audio_ff_index': 1, 'duration_ms': 1000,
                       'settings': {'engine': 'onecore', 'voice': 'fake', 'language': 'fr', 'region': 'fr-FR'},
                       'output': str(root / 'published.wav'), 'original_output': str(root / 'published-bg.wav')}
            request_path = root / 'request.json'
            request_path.write_text(json.dumps(request), encoding='utf-8')
            with patch('add_dub.core.subtitles.resolve_srt_for_video', return_value=str(path)), \
                 patch('add_dub.core.tts_generate.generate_dub_audio', side_effect=lambda src, out, *a, **k: wav(out)), \
                 patch('add_dub.adapters.ffmpeg.extract_audio_track', side_effect=RuntimeError('audio failure')), \
                 patch('sys.stderr', io.StringIO()):
                self.assertEqual(main(str(request_path)), 1)
            self.assertFalse(Path(request['output']).exists())
            self.assertFalse(Path(request['original_output']).exists())

    def test_gui_mux_uses_only_the_owned_partial_path(self):
        from add_dub.adapters.ffmpeg import dub_in_one_pass
        with tempfile.TemporaryDirectory() as root:
            partial = str(Path(root) / '.owned.partial.mkv')
            with patch.dict(os.environ, ADD_DUB_GUI_PARTIAL_OUTPUT=partial), \
                 patch('add_dub.adapters.ffmpeg._dub_in_one_pass') as mux, \
                 patch('add_dub.adapters.ffmpeg.validate_media'):
                dub_in_one_pass(output_video_path=partial, opts=DubOptions())
            self.assertEqual(mux.call_args.kwargs['output_video_path'], partial)

    def test_valid_ocr_xml_cache_survives_failed_replacement(self):
        from add_dub.adapters.downloads import resource
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'dictionary.xml'
            path.write_text('<dictionary/>', encoding='utf-8')
            with patch('urllib.request.urlopen') as network:
                self.assertEqual(resource('https://unused.invalid', path), str(path))
                network.assert_not_called()

    def test_offline_transport_never_opens_connection(self):
        from add_dub.adapters.http import VerifiedSession
        import requests
        with patch.dict(os.environ, ADD_DUB_OFFLINE='1'), patch.object(requests.Session, 'send') as send:
            with self.assertRaises(RuntimeError):
                VerifiedSession().get('https://example.invalid')
            send.assert_not_called()


class CliSafetyTests(unittest.TestCase):
    def test_reject_invalid_numbers_unknown_options_and_subtitles(self):
        from add_dub.cli.args import parse_args
        for extra in (['--bg-mix', 'nan'], ['--min-rate-tts', 'inf'], ['--max-rate-tts', '-1'],
                      ['--min-rate-tts', '3', '--max-rate-tts', '1'], ['--overwite'], ['--sub', 'oops']):
            with self.subTest(extra=extra), patch('sys.stderr', io.StringIO()):
                with self.assertRaises(SystemExit):
                    parse_args(['--batch'] + extra)

    def test_relative_input_is_resolved_under_input_folder(self):
        from add_dub.cli.batch import _gather_targets
        with tempfile.TemporaryDirectory() as root, patch.object(fs, 'INPUT_DIR', root), \
             patch('add_dub.cli.batch.ensure_base_dirs'):
            target = Path(root) / 'unique-audit-video.mp4'
            target.touch()
            self.assertEqual(_gather_targets([target.name], False), [(str(target), '')])

    def test_auto_accepts_central_srt_for_mp4(self):
        from add_dub.cli.batch import _build_services
        with tempfile.TemporaryDirectory() as root, patch.object(fs, 'SRT_DIR', root):
            (Path(root) / 'film.srt').write_text(srt(), encoding='utf-8')
            choice = _build_services(SimpleNamespace(sub_mode='auto')).choose_subtitle_source('film.mp4')
            self.assertEqual(choice, ('srt', None))

    def test_batch_continues_after_video_failure_and_returns_failure(self):
        from add_dub.cli import batch
        from add_dub.cli.args import parse_args
        args = parse_args(['--batch'])[0]
        services = Mock()
        services.choose_audio_track.return_value = 1
        services.choose_subtitle_source.return_value = ('srt', None)
        with patch.object(batch, '_apply_dirs_from_conf'), patch.object(batch, 'ensure_base_dirs'), \
             patch.object(batch, '_gather_targets', return_value=[('bad.mkv', ''), ('good.mkv', '')]), \
             patch.object(batch, '_build_services', return_value=services), \
             patch.object(batch, '_make_options', return_value=DubOptions()), \
             patch.object(batch, 'process_one_video', side_effect=[RuntimeError('failure'), 'out.mkv']) as process:
            self.assertEqual(batch.main(args), 1)
            self.assertEqual(process.call_count, 2)
