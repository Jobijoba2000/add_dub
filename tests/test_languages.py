import json
import unittest
from unittest.mock import patch, Mock
from add_dub.core.languages import source_languages, voice_language, language_code, track_language, language_name
from add_dub.core.languages import voice_locale, dubbed_track_title


class LanguageMetadataTests(unittest.TestCase):
    def test_dubbed_title_uses_voice_region(self):
        for voice, catalog, expected in (
            ('fr-CA-SylvieNeural', [], 'fr-CA'),
            ('MSTTS_V110_frFR_HortenseM', [], 'fr-FR'),
            ('token', [{'id': 'token', 'lang': ' FR_be '}], 'fr-BE'),
        ):
            with self.subTest(voice=voice):
                locale = voice_locale(voice, catalog)
                self.assertEqual(locale, expected)
                self.assertEqual(dubbed_track_title('fra', locale), f'French [{expected}]')
        self.assertEqual(voice_locale('fr', []), '')
        self.assertEqual(voice_locale('unknown', []), '')
        self.assertEqual(dubbed_track_title('fra', ''), 'French')
        self.assertEqual(dubbed_track_title('jpn', 'fr-FR'), 'Japanese')

    def test_metadata_formats_and_precedence(self):
        for value in ('ja', 'jpn', 'ja-JP', 'ja_JP', ' JPN ', 'Japanese', '日本語'):
            with self.subTest(value=value):
                self.assertEqual(track_language({'tags': {'LANGUAGE': value}}), 'jpn')
        self.assertEqual(track_language({'tags': {
            'LanguageIETF': 'fr-FR', 'language': 'jpn', 'title': 'English'}}), 'fra')
        self.assertEqual(track_language({'tags': {
            'language_bcp47': 'und', 'LANGUAGE': 'jpn', 'title': 'English'}}), 'jpn')
        self.assertEqual(language_code('zh-Hant-TW'), 'zho')

    def test_conservative_title_fallback(self):
        for title in ('Japanese', '日本語', 'Japanese (Original)', '[jpn] DTS 5.1'):
            self.assertEqual(track_language({'tags': {'language': 'und', 'title': title}}), 'jpn')
        for title in ('Original', 'Commentary about Japanese cinema', 'English / Japanese',
                      'not Japanese', 'xyz', ''):
            self.assertEqual(track_language({'tags': {'title': title}}), 'und')
        self.assertEqual(track_language({}), 'und')
        self.assertEqual(track_language({'tags': None}), 'und')

    def test_english_titles(self):
        for value in ('fr', 'fra', 'fre', 'FR_fr'):
            self.assertEqual(language_name(value), 'French')
        self.assertEqual(language_name('jpn'), 'Japanese')
        self.assertEqual(language_name('ger'), 'German')
        self.assertEqual(language_name('und'), 'Unknown language')

    def test_selected_tracks_not_first_tracks(self):
        streams = [
            {'index': 1, 'codec_type': 'audio', 'tags': {'language': 'eng'}},
            {'index': 2, 'codec_type': 'audio', 'tags': {'language': 'jpn'}},
            {'index': 3, 'codec_type': 'subtitle', 'tags': {'language': 'spa'}},
            {'index': 4, 'codec_type': 'subtitle', 'tags': {'language': 'fre'}},
        ]
        result = Mock(stdout=json.dumps({'streams': streams}))
        with patch('add_dub.core.languages.subprocess.run', return_value=result):
            self.assertEqual(source_languages('video.mkv', 2, ('mkv', 1)), ('jpn', 'fre'))
            self.assertEqual(source_languages('video.mp4', 2, ('stream', 4)), ('jpn', 'fre'))
            self.assertEqual(source_languages('video.mkv', 2, ('srt', 'external.srt')), ('jpn', 'und'))

    def test_voice_locale_and_unknown(self):
        self.assertEqual(voice_language('en-US-JennyNeural', []), 'eng')
        self.assertEqual(voice_language('MSTTS_V110_frFR_HortenseM', []), 'fra')
        self.assertEqual(voice_language('fr', []), 'fra')
        self.assertEqual(voice_language('unknown-token', []), 'und')
        self.assertEqual(voice_language('token', [{'id': 'token', 'lang': 'de-DE'}]), 'deu')
        self.assertEqual(language_code('Original'), 'und')
