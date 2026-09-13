"""Sélection d’une plage, essai isolé et lecture intégrée."""
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from PySide6.QtCore import Qt, Signal, QProcess, QProcessEnvironment, QTimer, QSize
from PySide6.QtGui import QPainter, QColor, QShortcut, QKeySequence, QIcon
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QProgressBar, QSlider, QToolTip, QSizePolicy, QGridLayout, QToolButton, QStyle

from add_dub.gui.model import BOOLS, batch_command
from add_dub.io import fs
from add_dub.progress import PREFIX, VideoProgress


def time_text(seconds):
    seconds = int(seconds)
    return f'{seconds // 60:02d}:{seconds % 60:02d}'


def time_seconds(text):
    import re
    if not re.fullmatch(r'\d+:[0-5]\d', text.strip()):
        raise ValueError('Utilisez mm:ss, par exemple 02:30.')
    minutes, seconds = map(int, text.split(':'))
    return minutes * 60 + seconds


class RangeBar(QWidget):
    changed = Signal(int, int)

    def __init__(self):
        super().__init__()
        self.duration, self.start, self.end = 1, 0, 1
        self.setMinimumHeight(18)
        self.setMinimumWidth(120)
        self.setMouseTracking(True)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor('#17412b'))
        left = round(self.width() * self.start / self.duration)
        right = round(self.width() * self.end / self.duration)
        painter.fillRect(left, 0, right - left, self.height(), QColor('#3bba72'))
        painter.setPen(QColor('#eeeeee'))
        painter.drawLine(left, 0, left, self.height())
        painter.drawLine(right - 1, 0, right - 1, self.height())

    def mousePressEvent(self, event):
        value = max(0, min(self.duration, round(event.position().x() / max(1, self.width()) * self.duration)))
        if event.button() == Qt.MouseButton.LeftButton:
            self.start = min(value, self.end - 1)
        elif event.button() == Qt.MouseButton.RightButton:
            self.end = max(value, self.start + 1)
        else:
            return
        self.update()
        self.changed.emit(self.start, self.end)

    def mouseMoveEvent(self, event):
        value = max(0, min(self.duration, round(event.position().x() / max(1, self.width()) * self.duration)))
        QToolTip.showText(event.globalPosition().toPoint(), time_text(value), self)

    def leaveEvent(self, event):
        QToolTip.hideText()
        super().leaveEvent(event)


class PreviewPane(QWidget):
    def __init__(self, dialog, tasks):
        super().__init__(dialog)
        self.dialog, self.tasks = dialog, tasks
        self.video = None
        self.player = None
        self.directory = None
        self.generation = 0
        self._closed = False
        self.stopping = False
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(self.process_error)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)
        self.name = QLabel('Sélectionnez une vidéo dans la liste.')
        self.name.setWordWrap(True)
        self.name.setMinimumHeight(30)
        header = QHBoxLayout()
        header.addWidget(self.name, 1)
        self.new_test = QPushButton('Nouvel essai')
        self.new_test.setAutoDefault(False)
        self.new_test.clicked.connect(self.clear_result)
        self.new_test.hide()
        header.addWidget(self.new_test)
        layout.addLayout(header)
        self.range_controls = QWidget()
        row = QHBoxLayout(self.range_controls)
        row.setContentsMargins(0, 0, 0, 0)
        self.bar = RangeBar()
        self.bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        row.addWidget(self.bar, 1)
        self.begin = QLineEdit('00:00')
        self.end = QLineEdit('00:30')
        for label, widget in [('Début', self.begin), ('Fin', self.end)]:
            widget.setMaximumWidth(85)
            widget.setAccessibleName(label + ' de l’essai (mm:ss)')
            widget.editingFinished.connect(self.input_range)
        row.addWidget(QLabel('Début'))
        row.addWidget(self.begin)
        row.addWidget(QLabel('Fin'))
        row.addWidget(self.end)
        self.duration_label = QLabel('Durée : --:--')
        row.addWidget(self.duration_label)
        self.test = QPushButton('Tester')
        self.test.setMinimumWidth(120)
        self.test.setEnabled(False)
        self.test.clicked.connect(self.run_test)
        row.addWidget(self.test)
        self.cancel = QPushButton('Arrêter l’essai')
        self.cancel.hide()
        self.cancel.clicked.connect(self.stop)
        row.addWidget(self.cancel)
        layout.addWidget(self.range_controls)
        self.bar.changed.connect(self.set_range)
        self.status = QLabel('')
        self.status.setWordWrap(True)
        self.status.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.status.hide()
        self.screen_container = QWidget()
        screen_layout = QGridLayout(self.screen_container)
        screen_layout.setContentsMargins(0, 0, 0, 0)
        screen_layout.setSpacing(0)
        screen_layout.setRowStretch(0, 1)
        self.screen_container.setStyleSheet('background: #000000;')
        self.screen = QWidget()
        self.screen.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
        self.screen.setMinimumHeight(240)
        self.screen.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.screen.setStyleSheet('background: black;')
        self.screen.hide()
        screen_layout.addWidget(self.screen, 0, 0)
        self.progress_extract = QLabel('Extraction de l’extrait : 0 %')
        self.progress_process = QLabel('Traitement du doublage : 0 %')
        for progress in (self.progress_extract, self.progress_process):
            progress.setAlignment(Qt.AlignmentFlag.AlignCenter)
            progress.setStyleSheet('font-size: 24px; font-weight: bold; color: white; background: transparent;')
            progress.hide()
        progress_box = QWidget()
        progress_layout = QVBoxLayout(progress_box)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.addWidget(self.progress_extract)
        progress_layout.addWidget(self.progress_process)
        screen_layout.addWidget(progress_box, 0, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.screen_container, 1)
        self.playback = QWidget()
        self.playback.setObjectName('previewPlayback')
        self.playback.setStyleSheet("""
            QWidget#previewPlayback { background: #161616; }
            QToolButton { border: none; background: transparent; padding: 0;
                          min-width: 34px; max-width: 34px; min-height: 34px; max-height: 34px; }
            QToolButton:hover, QToolButton:checked { background: #383838; }
            QSlider::groove:horizontal { height: 3px; background: #505050; }
            QSlider::sub-page:horizontal { background: #eeeeee; }
            QSlider::handle:horizontal { width: 10px; margin: -4px 0; background: white; border-radius: 5px; }
            QLabel { background: transparent; color: #eeeeee; }
        """)
        playback_layout = QVBoxLayout(self.playback)
        playback_layout.setContentsMargins(12, 4, 12, 6)
        playback_layout.setSpacing(0)
        self.seek = QSlider(Qt.Orientation.Horizontal)
        self.seek.setRange(0, 1000)
        self.seek.setFixedHeight(18)
        self.seek.setAccessibleName('Position dans l’extrait')
        self.seek.sliderReleased.connect(self.seek_to)
        playback_layout.addWidget(self.seek)
        playback = QHBoxLayout()
        playback.setSpacing(6)
        def button(icon, title, action):
            widget = QToolButton()
            widget.setIcon(self.control_icon(icon))
            widget.setIconSize(QSize(22, 22))
            widget.setToolTip(title)
            widget.setAccessibleName(title)
            widget.clicked.connect(action)
            playback.addWidget(widget)
            return widget
        self.pause = button(QStyle.StandardPixmap.SP_MediaPlay, 'Lecture / pause (Espace)', self.toggle_playback)
        button(QStyle.StandardPixmap.SP_MediaSeekBackward, 'Reculer de 5 secondes (gauche)', lambda: self.skip_seconds(-5))
        button(QStyle.StandardPixmap.SP_MediaSeekForward, 'Avancer de 5 secondes (droite)', lambda: self.skip_seconds(5))
        self.position = QLabel('00:00 / 00:00')
        playback.addWidget(self.position)
        playback.addStretch()
        self.subtitles = QToolButton()
        self.subtitles.setText('CC')
        self.subtitles.setAccessibleName('Sous-titres')
        self.subtitles.setCheckable(True)
        self.subtitles.setEnabled(False)
        self.subtitles.setStyleSheet('QToolButton { color: #eeeeee; font-weight: bold; } QToolButton:checked { border-bottom: 2px solid #3bba72; }')
        self.subtitles.setToolTip('Sous-titres indisponibles')
        self.subtitles.clicked.connect(self.toggle_subtitles)
        playback.addWidget(self.subtitles)
        self.mute = button(QStyle.StandardPixmap.SP_MediaVolume, 'Couper / rétablir le son (M)', lambda: None)
        self.mute.setCheckable(True)
        self.mute.toggled.connect(self.set_muted)
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setFixedHeight(18)
        self.volume.setValue(100)
        self.volume.setFixedWidth(90)
        self.volume.setAccessibleName('Volume')
        self.volume.valueChanged.connect(lambda value: self.player.set_volume(value) if self.player else None)
        playback.addWidget(self.volume)
        playback_layout.addLayout(playback)
        self.playback.hide()
        screen_layout.addWidget(self.playback, 1, 0)
        self.shortcuts = []
        for key, action in [('Space', self.toggle_playback), ('K', self.toggle_playback),
                            ('Left', lambda: self.skip_seconds(-5)), ('Right', lambda: self.skip_seconds(5)),
                            ('M', self.mute.toggle)]:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(action)
            shortcut.setEnabled(False)
            self.shortcuts.append(shortcut)
        self.timer = QTimer(self)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self.update_position)
        self.output_buffer = ''
        self.log = ''

    def choose_video(self, video):
        if self.process.state() != QProcess.ProcessState.NotRunning or self._closed:
            return
        if video and self.video and video.path == self.video.path:
            return
        self.generation += 1
        generation = self.generation
        self.video = video
        self.test.setEnabled(False)
        self.bar.setEnabled(False)
        if not video:
            self.name.setText('Sélectionnez une vidéo dans la liste.')
            return
        self.clear_result()
        self.name.setText(Path(video.path).name)
        self.name.setToolTip(video.path)
        self.status.setText('Lecture de la durée…')
        def work():
            result = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', video.path],
                                    capture_output=True, text=True, timeout=30,
                                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            duration = float(json.loads(result.stdout)['format']['duration'])
            if not math.isfinite(duration) or duration < 1:
                raise ValueError('Durée vidéo indisponible.')
            return int(duration)
        def done(duration, error):
            if generation != self.generation:
                return
            if error:
                self.status.setText(f'Durée indisponible : {error}')
                return
            self.bar.duration = duration
            self.set_range(0, min(30, duration))
            self.bar.setEnabled(True)
            self.test.setEnabled(True)
            self.duration_label.setText('Durée : ' + time_text(duration))
        self.tasks.run(self, work, done)

    def set_range(self, start, end):
        self.bar.start, self.bar.end = start, end
        self.begin.setText(time_text(start))
        self.end.setText(time_text(end))
        self.bar.update()

    def input_range(self):
        try:
            start, end = time_seconds(self.begin.text()), time_seconds(self.end.text())
            if not 0 <= start < end <= self.bar.duration:
                raise ValueError('La fin doit être après le début et dans la durée de la vidéo.')
            self.set_range(start, end)
            return True
        except ValueError as error:
            self.status.setText(str(error))
            return False

    def run_test(self):
        if not self.video or not self.input_range() or self.process.state() != QProcess.ProcessState.NotRunning:
            return
        try:
            self.dialog.save_current()
            settings = self.dialog.job.settings_for(self.video)
            if not settings.values.get('voice'):
                raise ValueError('Choisissez une voix pour cette configuration.')
            self.clear_result()
            from add_dub.gui.vlc_player import Player
            self.player = Player(self.screen.winId())
            Path(fs.TMP_DIR).mkdir(parents=True, exist_ok=True)
            self.directory = Path(tempfile.mkdtemp(prefix='gui-preview-', dir=fs.TMP_DIR)).resolve()
            settings.values['limit_duration_sec'] = ''
            flags = dict.fromkeys(BOOLS, False)
            flags.update(translate=settings.translate, overwrite=True)
            command = batch_command(settings.values, flags, [self.video.path], str(self.directory))
            env = QProcessEnvironment.systemEnvironment()
            for key, value in {'ADD_DUB_GUI_WORK_TMP': str(self.directory),
                               'ADD_DUB_GUI_PARTIAL_OUTPUT': str(self.directory / 'result.mkv'),
                               'ADD_DUB_PREVIEW_RANGE': json.dumps([self.bar.start, self.bar.end]),
                               'ADD_DUB_GUI_PROGRESS': '1', 'PYTHONIOENCODING': 'utf-8', 'PYTHONUNBUFFERED': '1',
                               'ADD_DUB_OPTIONS': os.path.abspath(os.getenv('ADD_DUB_OPTIONS', 'options.conf'))}.items():
                env.insert(key, value)
            self.process.setProcessEnvironment(env)
            self.process.setWorkingDirectory(fs.ROOT)
            self.output_buffer = self.log = ''
            self.tracker = VideoProgress()
            self.stopping = False
            self.progress_extract.setText('Extraction de l’extrait : 0 %')
            self.progress_process.setText('Traitement du doublage : 0 %')
            self.progress_extract.show()
            self.progress_process.show()
            self.screen.show()
            self.test.hide()
            self.cancel.show()
            self.bar.setEnabled(False)
            self.begin.setEnabled(False)
            self.end.setEnabled(False)
            self.status.setText('Préparation de l’extrait…')
            self.process.start(command[0], command[1:])
            self.process.closeWriteChannel()
        except Exception as error:
            # Une erreur de préparation doit rester visible dans l’onglet,
            # plutôt que laisser le clic sembler sans effet.
            self.status.setText(str(error))

    def read_output(self):
        data = bytes(self.process.readAllStandardOutput()).decode('utf-8', errors='replace')
        self.log = (self.log + data)[-6000:]
        self.output_buffer += data
        while '\n' in self.output_buffer:
            line, self.output_buffer = self.output_buffer.split('\n', 1)
            if PREFIX in line:
                try:
                    event = json.loads(line.split(PREFIX, 1)[1])
                    if event.get('event') == 'preview_extract':
                        self.progress_extract.setText(f"Extraction de l’extrait : {float(event.get('value', 0)):.1f} %")
                        continue
                    self.tracker.update(event)
                    self.progress_process.setText(f'Traitement du doublage : {self.tracker.percent:.1f} %')
                except (ValueError, KeyError):
                    pass

    def process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.log = self.process.errorString()
            self.finished(1, QProcess.ExitStatus.CrashExit)

    def finished(self, code, status):
        self.read_output()
        self.cancel.hide()
        self.bar.setEnabled(True)
        self.begin.setEnabled(True)
        self.end.setEnabled(True)
        self.test.show()
        output = self.directory / 'result.mkv' if self.directory else None
        if not self.stopping and code == 0 and output and output.is_file():
            self.progress_process.setText('Traitement du doublage : 100 %')
            self.screen.show()
            self.playback.show()
            try:
                self.player.play(str(output))
                self.range_controls.hide()
                self.new_test.show()
                for shortcut in self.shortcuts:
                    shortcut.setEnabled(True)
                self.pause.setFocus()
                self.player.set_volume(self.volume.value())
                self.player.set_mute(self.mute.isChecked())
                self.pause.setIcon(self.control_icon(QStyle.StandardPixmap.SP_MediaPause))
                self.progress_extract.hide()
                self.progress_process.hide()
                self.timer.start()
            except RuntimeError as error:
                self.status.setText(str(error))
        else:
            self.progress_extract.hide()
            self.progress_process.hide()
            self.status.setText('Essai arrêté.' if self.stopping else 'Échec de l’essai. ' + self.log[-1500:])
            self.clear_result()

    def stop(self):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.stopping = True
            subprocess.run(['taskkill', '/PID', str(self.process.processId()), '/T', '/F'],
                           capture_output=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
            self.process.waitForFinished(2000)

    def seek_to(self):
        if self.player:
            self.player.lib.libvlc_media_player_set_position(self.player.player, self.seek.value() / 1000)

    def update_position(self):
        self.refresh_subtitles()
        if self.player and not self.seek.isSliderDown():
            self.seek.setValue(max(0, round(self.player.lib.libvlc_media_player_get_position(self.player.player) * 1000)))
            icon = QStyle.StandardPixmap.SP_MediaPause if self.player.is_playing() else QStyle.StandardPixmap.SP_MediaPlay
            self.pause.setIcon(self.control_icon(icon))
            current = self.player.get_time()
            total = self.player.get_length()
            if current >= 0 and total > 0:
                self.position.setText(f'{time_text(current / 1000)} / {time_text(total / 1000)}')

    def control_icon(self, standard):
        pixmap = self.style().standardIcon(standard).pixmap(QSize(22, 22))
        painter = QPainter(pixmap)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(pixmap.rect(), QColor('#eeeeee'))
        painter.end()
        return QIcon(pixmap)

    def refresh_subtitles(self):
        available = bool(self.player and self.player.subtitle_tracks())
        enabled = bool(available and self.player.subtitles_enabled())
        self.subtitles.setEnabled(available)
        self.subtitles.setChecked(enabled)
        self.subtitles.setToolTip(('Masquer les sous-titres' if enabled else 'Afficher les sous-titres')
                                 if available else 'Sous-titres indisponibles')

    def toggle_subtitles(self, enabled):
        if self.player:
            self.player.set_subtitles(enabled)
        self.refresh_subtitles()

    def set_muted(self, muted):
        if self.player:
            self.player.set_mute(muted)
        icon = QStyle.StandardPixmap.SP_MediaVolumeMuted if muted else QStyle.StandardPixmap.SP_MediaVolume
        self.mute.setIcon(self.control_icon(icon))

    def skip_seconds(self, seconds):
        if self.player and self.playback.isVisible():
            total = self.player.get_length()
            if total > 0:
                target = max(0, min(total - 1, self.player.get_time() + seconds * 1000))
                self.player.lib.libvlc_media_player_set_position(self.player.player, target / total)

    def toggle_playback(self):
        if not self.player:
            return
        if self.player.is_playing():
            self.pause_playback()
        else:
            self.player.play_current()
            self.pause.setIcon(self.control_icon(QStyle.StandardPixmap.SP_MediaPause))

    def pause_playback(self):
        if self.player:
            self.player.pause()
            self.pause.setIcon(self.control_icon(QStyle.StandardPixmap.SP_MediaPlay))

    def stop_playback(self):
        if self.player:
            self.player.stop()
            self.pause.setIcon(self.control_icon(QStyle.StandardPixmap.SP_MediaPlay))

    def clear_result(self):
        self.timer.stop()
        self.subtitles.setChecked(False)
        self.subtitles.setEnabled(False)
        self.range_controls.show()
        self.new_test.hide()
        self.test.setText('Tester')
        for shortcut in self.shortcuts:
            shortcut.setEnabled(False)
        if self.player:
            self.player.close()
            self.player = None
        self.screen.hide()
        self.progress_extract.hide()
        self.progress_process.hide()
        self.playback.hide()
        if self.directory and self.directory.parent == Path(fs.TMP_DIR).resolve() and self.directory.name.startswith('gui-preview-'):
            shutil.rmtree(self.directory, ignore_errors=True)
            self.directory = None

    def shutdown(self):
        self._closed = True
        self.generation += 1
        self.stop()
        self.clear_result()
