"""Essai réel de l'aperçu GUI : extraction, doublage, mux et lecture mpv."""
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from add_dub.cli.args import parse_args
from add_dub.config.defaults import get_system_default_voice_id
from add_dub.gui.dialog import ConfigureDialog
from add_dub.gui.model import Job, Settings
from add_dub.gui.widgets import Async
from add_dub.io import fs


def main():
    app = QApplication([])
    fs.ensure_base_dirs()
    voice = get_system_default_voice_id()
    assert voice, 'Voix OneCore nécessaire.'
    with tempfile.TemporaryDirectory(prefix='mpv-preview-test-') as directory:
        directory = Path(directory)
        srt = directory / 'dialogues.srt'
        srt.write_text('1\n00:00:01,000 --> 00:00:02,500\nBonjour.\n\n2\n00:00:03,000 --> 00:00:04,500\nAu revoir.\n', encoding='utf-8')
        video = directory / 'essai.mkv'
        subprocess.run([str(ROOT / 'tools/ffmpeg/bin/ffmpeg.exe'), '-v', 'error', '-y',
                        '-f', 'lavfi', '-i', 'testsrc2=size=640x360:rate=25:duration=8',
                        '-f', 'lavfi', '-i', 'sine=frequency=440:duration=8', '-i', str(srt),
                        '-map', '0:v', '-map', '1:a', '-map', '2:s',
                        '-c:v', 'mpeg4', '-c:a', 'aac', '-c:s', 'srt', str(video)],
                       check=True, creationflags=subprocess.CREATE_NO_WINDOW)
        args = parse_args(['--gui', '--tts-engine', 'onecore', '--voice', voice, '--no-translate'])[0]
        tasks = Async()
        dialog = ConfigureDialog(Job([str(video)], Settings.from_args(args), str(directory)), tasks)
        dialog.show()
        pane = dialog.preview

        def wait_for(predicate, seconds=10):
            deadline = time.monotonic() + seconds
            while not predicate():
                if time.monotonic() > deadline:
                    raise AssertionError(pane.status.text() + '\n' + pane.log)
                QTest.qWait(30)

        try:
            wait_for(lambda: dialog.loaded and not dialog.editor.voice.loading)
            dialog.editor.setCurrentWidget(pane)
            pane.choose_video(dialog.reference)
            wait_for(lambda: pane.test.isEnabled())
            pane.set_range(0, 6)
            pane.run_test()
            wait_for(lambda: pane.player and pane.playback.isVisible() and pane.player.is_playing(), 45)
            work = pane.directory
            assert (work / 'result.mkv').is_file()
            pane.pause_playback()
            wait_for(lambda: pane.player.get_state() == 4)
            pane.seek.setValue(500)
            pane.seek_to()
            wait_for(lambda: abs(pane.player.get_time() - pane.player.get_length() / 2) < 300)
            pane.volume.setValue(37)
            assert float(pane.player._get('volume')) == 37
            pane.mute.setChecked(True)
            assert pane.player.is_muted()
            pane.mute.setChecked(False)
            assert not pane.player.is_muted()
            wait_for(lambda: bool(pane.player.subtitle_tracks()))
            pane.toggle_subtitles(False)
            assert not pane.player.subtitles_enabled()
            pane.toggle_subtitles(True)
            assert pane.player.subtitles_enabled()
            pane.skip_seconds(-5)
            wait_for(lambda: pane.player.get_time() < 500)
            pane.toggle_playback()
            wait_for(pane.player.is_playing)
            pane.clear_result()
            assert pane.player is None and not work.exists()
            print('OK aperçu GUI : pipeline OneCore complet, lecture mpv, pause, navigation, volume, muet, sous-titres et nettoyage.')
        finally:
            dialog.close()
            app.processEvents()


if __name__ == '__main__':
    main()
