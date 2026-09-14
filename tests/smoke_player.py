"""Essai du lecteur sur une courte vidéo temporaire. Ferme la fenêtre à la fin."""
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import wave
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt, QTimer
from add_dub.player.gui.window import Window
from add_dub.player.gui.generation_dialog import GenerationDialog
from add_dub.core.subtitles import resolve_srt_for_video
from add_dub.config.defaults import get_system_default_voice_id


def main():
    app = QApplication([])
    with tempfile.TemporaryDirectory(prefix='add-dub-player-test-') as directory:
        video = Path(directory) / 'essai vidéo.mkv'
        english = Path(directory) / 'english.srt'
        french = Path(directory) / 'french.srt'
        english.write_text('1\n00:00:01,000 --> 00:00:02,500\nHello world.\n', encoding='utf-8')
        french.write_text('1\n00:00:01,000 --> 00:00:02,500\nBonjour.\n\n2\n00:00:03,000 --> 00:00:04,500\nAu revoir.\n', encoding='utf-8')
        subprocess.run([str(ROOT/'tools/ffmpeg/bin/ffmpeg.exe'), '-v', 'error', '-y',
                        '-f', 'lavfi', '-i', 'testsrc2=size=640x360:rate=25:duration=6',
                        '-f', 'lavfi', '-i', 'sine=frequency=440:duration=6',
                        '-i', str(english), '-i', str(french),
                        '-map', '0:v', '-map', '1:a', '-map', '2:s', '-map', '3:s',
                        '-c:v', 'mpeg4', '-c:a', 'aac', '-c:s', 'srt',
                        '-metadata:s:s:0', 'language=eng', '-metadata:s:s:1', 'language=fra',
                        '-disposition:s:0', 'default', '-disposition:s:1', '0', str(video)],
                       check=True, creationflags=subprocess.CREATE_NO_WINDOW)
        window = Window()
        window.show()

        def wait_for(predicate):
            end = time.monotonic() + 8
            while not predicate():
                if time.monotonic() > end:
                    raise AssertionError('Délai dépassé, état mpv : ' + str(window.player.get_state()))
                QTest.qWait(50)

        try:
            window.open_video(str(video))
            wait_for(lambda: window.player.is_playing() and window.player.get_time() > 100)
            window.playback.toggle_pause()
            wait_for(lambda: window.player.get_state() == 4)
            window.playback.seek(.5)
            wait_for(lambda: abs(window.player.get_time()-3000) < 400)
            window.volume.setValue(35)
            window.toggle_mute()
            wait_for(window.player.is_muted)
            window.toggle_mute()
            wait_for(lambda: not window.player.is_muted())
            window.playback.toggle_pause()
            wait_for(window.player.is_playing)
            window.fullscreen()
            QTest.qWait(100)
            assert window.isFullScreen()
            window.fullscreen()
            QTest.qWait(100)
            assert not window.isFullScreen()
            window.open_video(str(video))
            wait_for(lambda: window.player.is_playing() and 0 <= window.player.get_time() < 2000)
            assert window.controls.isVisible()
            wait_for(lambda: len(window.player.embedded_subtitles()) == 2)
            tracks = window.player.embedded_subtitles()
            print('Langue système :', window.system_language, 'pistes :', tracks,
                  'sélection :', window.player.current_subtitle_track())
            if window.system_language == 'fr':
                assert window.player.current_subtitle_track() == tracks[1]['id']
            # Explicitly choose another track, then restore French: TTS must
            # use the actual selection, independently of the default flag.
            assert window.player.select_subtitle_track(tracks[0]['id'])
            assert window.player.select_subtitle_track(tracks[1]['id'])
            window.player.ensure_paused()
            wait_for(lambda: window.player.get_state() == 4)
            extracted = Path(directory) / 'selected.srt'
            from unittest.mock import patch as patch_fs
            with patch_fs('add_dub.io.fs.SRT_DIR', directory):
                extracted = Path(resolve_srt_for_video(str(video), ('mkv', 1)))
            assert 'Bonjour' in extracted.read_text(encoding='utf-8')
            assert 'Hello' not in extracted.read_text(encoding='utf-8')
            audio_tracks = [t for t, _ in window.player.audio_tracks() if t >= 0]
            assert audio_tracks
            assert window.player.select_audio_track(-1)
            assert window.player.current_audio_track() == -1
            assert window.player.select_audio_track(audio_tracks[0])
            assert window.player.current_audio_track() == audio_tracks[0]
            assert window.player.select_subtitle_track(-1)
            assert window.player.current_subtitle_track() == -1
            assert window.player.select_subtitle_track(tracks[1]['id'])
            if '--tts' not in sys.argv:
                print('OK mpv : lecture, pause, navigation, volume, muet, plein écran, réouverture, pistes audio et sous-titres, français automatique, extraction FFmpeg.')
                return
            voice = get_system_default_voice_id()
            assert voice, 'Une voix OneCore est nécessaire au test réel.'
            if '--quick' in sys.argv:
                dialogs = []
                settings = dict(engine='onecore', voice=voice, language='fr', region='fr-FR',
                                ducking_db=-8, min_rate_tts=1, max_rate_tts=1.5, tts_mix=1.2, bg_mix=.7)
                def make_dialog(*args, **kwargs):
                    result = GenerationDialog(*args, **kwargs)
                    dialogs.append(result)
                    return result
                watchdog = QTimer()
                watchdog.setSingleShot(True)
                watchdog.timeout.connect(lambda: dialogs[-1].reject() if dialogs else None)
                window.activateWindow()
                window.setFocus()
                QTest.qWait(300)
                watchdog.start(45000)
                with patch('add_dub.player.gui.window.load_settings', return_value=settings), \
                     patch('add_dub.player.gui.window.GenerationDialog', side_effect=make_dialog):
                    QTest.keyClick(window, Qt.Key.Key_D, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
                watchdog.stop()
                assert len(dialogs) == 1, 'Le raccourci doit ouvrir le traitement.'
                dialog = dialogs[0]
                assert dialog.choice == 'restart', dialog.log_tail
                assert not dialog.isVisible()
                paths = (dialog.output_path, dialog.original_path)
                assert all(path and Path(path).is_file() for path in paths)
                wait_for(lambda: window.player.is_playing() and 0 < window.player.get_time() < 1500)
                graph = window.player._get('lavfi-complex')
                assert "weights='0.700000 1.200000'" in graph, graph
                window.player.stop()
                QTest.qWait(100)
                for path in paths:
                    Path(path).unlink()
                print('OK raccourci Ctrl+Maj+D : TTS réel, ducking, fermeture automatique, deux WAV et niveaux BG/TTS, reprise au début.')
                return
            dialog = GenerationDialog({'video': str(video), 'ordinal': 1, 'track_count': 2,
                'audio_ff_index': window.player.selected_audio_ff_index(),
                'duration_ms': window.player.get_length(), 'settings': {
                    'engine': 'onecore', 'voice': voice, 'language': 'fr', 'region': 'fr-FR'}}, window)
            dialog.show()
            deadline = time.monotonic() + 45
            while dialog.running and time.monotonic() < deadline:
                QTest.qWait(50)
            if dialog.running:
                print(dialog.bar.format(), dialog.label.text(), dialog.log_tail, flush=True)
                dialog.reject()
                while dialog.running:
                    QTest.qWait(50)
                raise AssertionError('Génération bloquée')
            assert dialog.output_path, dialog.label.text()
            assert dialog.original_path and Path(dialog.original_path).is_file()
            assert dialog.restart_button.isVisible() and dialog.continue_button.isVisible()
            assert not dialog.button.isVisible()
            assert dialog.bar.value() == 1000
            assert window.player.get_state() == 4
            with wave.open(dialog.output_path) as wav:
                assert abs(wav.getnframes()/wav.getframerate() - window.player.get_length()/1000) < .1
                audio = wav.readframes(wav.getnframes())
                assert any(audio), 'Le WAV ne doit pas être silencieux.'
            Path(dialog.output_path).unlink()
            Path(dialog.original_path).unlink()
            dialog.close()
            print('OK : sélection langue système, extraction piste française, TTS OneCore, WAV complet, progression et pause maintenue.')
            print('OK : ouverture, pause, navigation, volume, muet, reprise, plein écran et réouverture.')
        finally:
            window.close()
            app.processEvents()


if __name__ == '__main__':
    main()
