import unittest
from unittest.mock import patch
from add_dub import i18n
from add_dub.gui.translations import ui, video_count
from add_dub.progress import VideoProgress


class InterfaceLanguageTests(unittest.TestCase):
    def test_controls_follow_configured_language(self):
        for language, expected in [('fr', 'Ouvrir'), ('en', 'Open'), ('es', 'Abrir'),
                                   ('de', 'Öffnen'), ('it', 'Apri')]:
            with self.subTest(language=language), patch.object(i18n, '_CURRENT_LANG', language):
                self.assertEqual(ui('Ouvrir'), expected)

    def test_explanations_follow_configured_language(self):
        for language, expected in [('fr', 'La vidéo est en pause.'),
                                   ('en', 'The video is paused.'),
                                   ('es', 'El vídeo está en pausa.'),
                                   ('de', 'Das Video ist pausiert.'),
                                   ('it', 'Il video è in pausa.')]:
            with self.subTest(language=language), patch.object(i18n, '_CURRENT_LANG', language):
                self.assertEqual(ui('La vidéo est en pause.'), expected)

    def test_video_plurals_and_completed_queue_message(self):
        text = 'Traitement terminé : {videos}. Consultez l’onglet « Terminé » ou ajoutez de nouvelles vidéos avec « Ouvrir ».'
        for language, single, plural, completed in [
                ('fr', '1 vidéo', '2 vidéos', '2 vidéos terminées'),
                ('en', '1 video', '2 videos', '2 videos completed'),
                ('es', '1 vídeo', '2 vídeos', '2 vídeos completados'),
                ('de', '1 Video', '2 Videos', '2 Videos abgeschlossen'),
                ('it', '1 video', '2 video', '2 video completati')]:
            with self.subTest(language=language), patch.object(i18n, '_CURRENT_LANG', language):
                self.assertEqual(video_count(1), single)
                self.assertEqual(video_count(2), plural)
                self.assertEqual(video_count(2, completed=True), completed)
                message = ui(text).format(videos=video_count(2, completed=True))
                self.assertIn(completed, message)
                if language != 'fr':
                    self.assertNotIn('Consultez', message)

    def test_progress_language_is_resolved_when_stage_arrives(self):
        progress = VideoProgress()
        with patch.object(i18n, '_CURRENT_LANG', 'es'):
            progress.update({'event': 'stage', 'name': 'translation'})
            self.assertIn('Traducción', progress.text)

    def test_settings_validation_formats_ranges_in_configured_language(self):
        from add_dub.config.editor import DEFAULTS, validate_settings
        values = {**DEFAULTS, 'bg': '20.0', 'audio_bitrate': '1.5', 'input_dir': ''}
        for language, range_message, integer_message, empty_message in [
                ('es', 'Valor esperado: de 0 a 10 (punto decimal).',
                 'Valor esperado: de 32 a 640 (entero).', 'Este campo no puede estar vacío.'),
                ('de', 'Erwarteter Wert: 0 bis 10 (Dezimalpunkt).',
                 'Erwarteter Wert: 32 bis 640 (ganze Zahl).', 'Dieses Feld darf nicht leer sein.'),
                ('it', 'Valore previsto: da 0 a 10 (punto decimale).',
                 'Valore previsto: da 32 a 640 (intero).', 'Questo campo non può essere vuoto.')]:
            with self.subTest(language=language), patch.object(i18n, '_CURRENT_LANG', language):
                errors = validate_settings(values)
                self.assertEqual(errors['bg'], range_message)
                self.assertEqual(errors['audio_bitrate'], integer_message)
                self.assertEqual(errors['input_dir'], empty_message)
