"""Contrats du parcours SRT antérieur à l'audit (révision 0f067bf)."""
from contextlib import ExitStack
from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from add_dub.core import subtitles, pipeline, translation
from add_dub.core.options import DubOptions
from add_dub.io import fs
from add_dub.io.work import work_directory


def content(text):
    return f'1\n00:00:00,100 --> 00:00:01,000\n{text}\n'


class PersistentSubtitleWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.central = self.root / 'srt'
        self.central.mkdir()
        self.source = self.root / 'input'
        self.source.mkdir()
        self.video = self.source / 'film.mkv'
        self.video.touch()
        self.target = self.central / 'film.srt'
        self.stack.enter_context(patch.object(fs, 'SRT_DIR', str(self.central)))
        self.stack.enter_context(patch.object(fs, 'INPUT_DIR', str(self.source)))

    def test_central_srt_precedes_sidecar_and_survives_work_cleanup(self):
        self.target.write_text(content('central'), encoding='utf-8')
        self.video.with_suffix('.srt').write_text(content('sidecar'), encoding='utf-8')
        with work_directory(self.root):
            result = subtitles.resolve_srt_for_video(str(self.video), ('srt', None))
        self.assertEqual(result, str(self.target))
        self.assertEqual(subtitles.parse_srt_file(result)[0][2], 'central')
        self.assertTrue(self.target.exists())

    def test_sidecar_is_copied_cleaned_and_reused_without_changing_source(self):
        sidecar = self.video.with_suffix('.srt')
        original = content('<i>été</i>').encode('cp1252')
        sidecar.write_bytes(original)
        result = subtitles.resolve_srt_for_video(str(self.video), ('srt', None))
        self.assertEqual(result, str(self.target))
        self.assertEqual(sidecar.read_bytes(), original)
        sidecar.unlink()
        self.assertEqual(subtitles.resolve_srt_for_video(str(self.video), ('srt', None)), result)
        self.assertEqual(subtitles.parse_srt_file(result)[0][2], 'été')

    def test_explicit_matching_srt_replaces_central_and_unrelated_selection_falls_back(self):
        chosen = self.source / 'film.fr.srt'
        chosen.write_text(content('chosen'), encoding='utf-8')
        self.target.write_text(content('old'), encoding='utf-8')
        self.assertEqual(subtitles.resolve_srt_for_video(str(self.video), ('srt', str(chosen))), str(self.target))
        other = self.source / 'another.srt'
        other.write_text(content('unrelated'), encoding='utf-8')
        subtitles.resolve_srt_for_video(str(self.video), ('srt', str(other)))
        self.assertEqual(subtitles.parse_srt_file(str(self.target))[0][2], 'chosen')

    def test_all_mkv_conversions_publish_persistent_srt_and_gui_offers_it_again(self):
        from add_dub.gui.model import Video, inspect_video
        for codec in ('S_TEXT/UTF8', 'S_TEXT/ASS', 'S_HDMV/PGS', 'S_VOBSUB'):
            with self.subTest(codec=codec):
                self.target.write_text(content('previous'), encoding='utf-8')
                info = {'tracks': [{'type': 'subtitles', 'id': 7,
                                    'properties': {'codec_id': codec, 'language': 'fra'}}]}
                def run(command, **kwargs):
                    if command[0] == 'ffmpeg':
                        Path(command[-1]).write_text(content(codec), encoding='utf-8')
                    return SimpleNamespace(returncode=0, stdout='', stderr='')
                def ocr(source, destination, **kwargs):
                    Path(destination).write_text(content(codec), encoding='utf-8')
                    return True
                with work_directory(self.root), patch.object(subtitles, 'mkvmerge_identify_json', return_value=info), \
                     patch.object(subtitles, '_find_exe', return_value='mkvextract'), \
                     patch.object(subtitles.subprocess, 'run', side_effect=run), \
                     patch.object(subtitles, 'subtitle_edit_ocr', side_effect=ocr):
                    result = subtitles.resolve_srt_for_video(str(self.video), ('mkv', 0))
                self.assertEqual(result, str(self.target))
                self.assertEqual(subtitles.parse_srt_file(result)[0][2], codec)
                response = SimpleNamespace(returncode=0, stderr='', stdout=json.dumps({'streams': [
                    {'index': 1, 'codec_type': 'audio', 'codec_name': 'ac3'},
                    {'index': 2, 'codec_type': 'subtitle', 'codec_name': codec}]}))
                with patch('add_dub.gui.model.subprocess.run', return_value=response):
                    detected = inspect_video(Video(path=str(self.video)))
                self.assertFalse(detected.error)
                self.assertEqual(detected.subtitles[0].value, 'srt')
                self.assertIn('film.srt', detected.subtitles[0].label)
                with patch.object(subtitles, 'extract_first_subtitle_to_srt_into_input') as extract:
                    self.assertEqual(subtitles.resolve_srt_for_video(str(self.video), ('srt', None)), result)
                    extract.assert_not_called()

    def test_stream_selection_keeps_persistent_name_and_exact_track(self):
        def extract(command, **kwargs):
            self.assertEqual(command[command.index('-map') + 1], '0:4')
            Path(command[-1]).write_text(content('stream'), encoding='utf-8')
        with work_directory(self.root), patch.object(subtitles.subprocess, 'run', side_effect=extract):
            result = subtitles.resolve_srt_for_video(str(self.video), ('stream', 4))
        self.assertEqual(result, str(self.target))
        self.assertTrue(self.target.exists())

    def test_vobsub_fallback_keeps_persistent_srt(self):
        info = {'tracks': [{'type': 'subtitles', 'id': 3, 'properties': {'codec_id': 'S_VOBSUB'}}]}
        def fallback(base, **kwargs):
            result = base + '.srt'
            Path(result).write_text(content('fallback'), encoding='utf-8')
            return result
        with patch.object(subtitles, 'mkvmerge_identify_json', return_value=info), \
             patch.object(subtitles, '_find_exe', return_value='mkvextract'), \
             patch.object(subtitles.subprocess, 'run'), \
             patch.object(subtitles, 'subtitle_edit_ocr', return_value=False), \
             patch.object(subtitles, 'vobsub2srt_ocr', side_effect=fallback):
            self.assertEqual(subtitles.resolve_srt_for_video(str(self.video), ('mkv', 0)), str(self.target))
        self.assertEqual(subtitles.parse_srt_file(str(self.target))[0][2], 'fallback')

    def test_central_srt_makes_video_eligible_without_embedded_subtitles(self):
        self.target.write_text(content('available'), encoding='utf-8')
        with patch.object(subtitles, 'mkv_has_subtitle_track', return_value=False):
            self.assertIn(self.video.name, subtitles.list_input_videos())

    def test_batch_srt_priority_and_auto_selection_match_previous_version(self):
        from add_dub.cli.batch import _build_services
        self.target.write_text(content('central'), encoding='utf-8')
        srt_services = _build_services(SimpleNamespace(sub_mode='srt'))
        auto_services = _build_services(SimpleNamespace(sub_mode='auto'))
        self.assertEqual(srt_services.choose_subtitle_source(str(self.video)), ('srt', str(self.target)))
        self.assertEqual(auto_services.choose_subtitle_source(str(self.video)), ('mkv', 0))
        self.video.with_suffix('.srt').write_text(content('sidecar'), encoding='utf-8')
        self.assertEqual(auto_services.choose_subtitle_source(str(self.video)), ('srt', None))
        self.assertEqual(srt_services.choose_subtitle_source(str(self.video)), ('srt', str(self.target)))


class TranslationWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(patch.object(fs, 'SRT_DIR', str(self.root)))
        self.stack.enter_context(patch.object(fs, 'TMP_DIR', str(self.root)))
        self.source = self.root / 'film.srt'
        self.source.write_text(content('Hello'), encoding='utf-8')
        self.cached = self.root / 'film.srt.fr.srt'
        self.ui = Mock()
        self.services = Mock(ui=self.ui)
        self.services.resolve_srt_for_video.return_value = str(self.source)
        self.opts = DubOptions(audio_ffmpeg_index=1, sub_choice=('srt', None), translate=True,
                               translate_from='en', translate_to='fr', batch_mode=True)
        self.stack.enter_context(patch.object(pipeline, 'list_available_voices', return_value=[]))
        self.stack.enter_context(patch('add_dub.core.languages.source_languages', return_value=('eng', 'eng')))
        self.stack.enter_context(patch.object(pipeline, 'extract_audio_track'))
        self.stack.enter_context(patch('add_dub.adapters.ffmpeg.media_duration', return_value=2))
        self.stack.enter_context(patch.object(pipeline, 'lower_audio_during_subtitles'))
        self.mux = self.stack.enter_context(patch.object(pipeline, 'dub_in_one_pass'))
        self.translate = self.stack.enter_context(patch.object(translation, 'translate_subtitles', return_value=[(.1, 1, 'Bonjour')]))

    def run_pipeline(self, **options):
        return pipeline.process_one_video(input_video_path=str(self.root / 'film.mkv'),
            input_video_name='film.mkv', output_dir_path=str(self.root / 'out'),
            opts=replace(self.opts, **options), svcs=self.services)

    def test_translation_keeps_historical_filename_and_is_reused_next_run(self):
        self.run_pipeline()
        self.assertTrue(self.cached.exists())
        self.assertEqual(self.mux.call_args.kwargs['subtitle_srt_path'], str(self.cached))
        self.run_pipeline()
        self.translate.assert_called_once()
        self.assertFalse((self.root / '.translations').exists())

    def test_existing_translation_reused_without_model_or_source_detection(self):
        self.cached.write_text(content('Manually corrected'), encoding='utf-8')
        self.run_pipeline(translate_from=None)
        self.translate.assert_not_called()
        self.assertEqual(subtitles.parse_srt_file(str(self.cached))[0][2], 'Manually corrected')

    def test_overwrite_or_disabled_reuse_regenerates_translation(self):
        for options in ({'overwrite': True}, {'reuse_translated_subs': False}):
            with self.subTest(options=options):
                self.cached.write_text(content('old'), encoding='utf-8')
                self.translate.reset_mock()
                self.run_pipeline(**options)
                self.translate.assert_called_once()
                self.assertEqual(subtitles.parse_srt_file(str(self.cached))[0][2], 'Bonjour')

    def test_interactive_reuse_confirmation_is_restored(self):
        self.cached.write_text(content('kept'), encoding='utf-8')
        self.ui.ask_yes_no.return_value = True
        self.run_pipeline(batch_mode=False, ask_reuse_subs=True)
        self.ui.ask_yes_no.assert_called_once()
        self.translate.assert_not_called()

    def test_declining_translation_reuse_regenerates_it(self):
        self.cached.write_text(content('old'), encoding='utf-8')
        self.ui.ask_yes_no.return_value = False
        self.run_pipeline(batch_mode=False, ask_reuse_subs=True)
        self.translate.assert_called_once()
        self.assertEqual(subtitles.parse_srt_file(str(self.cached))[0][2], 'Bonjour')

    def test_unavailable_translation_offers_retry_and_original_fallback(self):
        self.translate.return_value = None
        self.ui.ask_yes_no.return_value = False
        self.run_pipeline(batch_mode=False)
        self.ui.ask_yes_no.assert_called_once()
        self.assertEqual(self.mux.call_args.kwargs['subtitle_srt_path'], str(self.source))

    def test_preview_translation_is_temporary_and_restores_central_directory(self):
        def excerpt(video, srt, audio, start, end, directory, **kwargs):
            path = Path(directory) / 'preview-source.srt'
            path.write_text(content('preview'), encoding='utf-8')
            return video, str(path), audio
        with patch.dict(os.environ, ADD_DUB_PREVIEW_RANGE='[0, 2]'), \
             patch('add_dub.core.preview.prepare_excerpt', side_effect=excerpt):
            self.run_pipeline()
        used = Path(self.mux.call_args.kwargs['subtitle_srt_path'])
        self.assertEqual(used.name, 'preview-source.srt.fr.srt')
        self.assertFalse(used.exists())
        self.assertEqual(fs.SRT_DIR, str(self.root))
        self.assertFalse(self.cached.exists())

    def test_same_language_skips_and_failure_keeps_original_as_before(self):
        self.run_pipeline(translate_from='fr')
        self.translate.assert_not_called()
        self.assertEqual(self.mux.call_args.kwargs['subtitle_srt_path'], str(self.source))
        self.translate.side_effect = RuntimeError('translation unavailable')
        self.run_pipeline()
        self.assertEqual(self.mux.call_args.kwargs['subtitle_srt_path'], str(self.source))
        self.assertFalse(self.cached.exists())

    def test_shifted_srt_and_translation_remain_available(self):
        self.run_pipeline(offset_ms=250)
        shifted = self.root / 'film.shifted.srt'
        translated = self.root / 'film.shifted.srt.fr.srt'
        self.assertTrue(shifted.exists())
        self.assertTrue(translated.exists())
        self.assertAlmostEqual(subtitles.parse_srt_file(str(shifted))[0][0], .35)
