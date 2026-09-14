from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QSize, QLocale
from PySide6.QtGui import QShortcut, QKeySequence, QPainter, QColor, QIcon, QActionGroup
from PySide6.QtWidgets import (QMainWindow, QWidget, QFrame, QVBoxLayout, QHBoxLayout,
                              QLabel, QSlider, QToolButton, QStyle, QFileDialog, QMenu, QMessageBox)
from add_dub.adapters.mpv import Player
from add_dub.player.core.playback import Playback
from add_dub.player.config.defaults import APP_NAME, DEFAULT_VOLUME
from add_dub.player.io.fs import ensure_base_dirs
from add_dub.player.io.settings import load_settings
from .theme import STYLE
from add_dub.gui.widgets import Async
from .voice_dialog import VoiceDialog
from .generation_dialog import GenerationDialog


def time_text(milliseconds):
    seconds = max(0, milliseconds // 1000)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return f'{hours}:{minutes:02d}:{seconds:02d}' if hours else f'{minutes}:{seconds:02d}'


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        ensure_base_dirs()
        self.setWindowTitle(APP_NAME)
        self.resize(1000, 620)
        self.setMinimumSize(640, 360)
        self.setStyleSheet(STYLE)
        self.screen = QWidget(self)
        self.screen.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
        self.screen.setStyleSheet('background: black;')
        self.screen.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.screen.customContextMenuRequested.connect(self.context_menu)
        self.setCentralWidget(self.screen)
        self.system_language = QLocale.system().name().split('_')[0]
        self.player = Player(int(self.screen.winId()), subtitle_language=self.system_language)
        self.playback = Playback(self.player)
        self.tasks = Async(self)
        try:
            self.voice_settings = load_settings()
        except (OSError, ValueError, TypeError):
            self.voice_settings = None

        # Native child above the video output: controls stay inside the player.
        self.controls = QFrame(self.screen)
        self.controls.setObjectName('controls')
        self.controls.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
        self.controls.setStyleSheet(STYLE)
        layout = QVBoxLayout(self.controls)
        layout.setContentsMargins(12, 8, 12, 8)
        self.seek = QSlider(Qt.Orientation.Horizontal)
        self.seek.setRange(0, 10000)
        self.seek.setAccessibleName('Position dans la vidéo')
        self.seek.sliderReleased.connect(lambda: self.playback.seek(self.seek.value()/10000))
        layout.addWidget(self.seek)
        row = QHBoxLayout()
        self.open_button = self.button(QStyle.StandardPixmap.SP_DialogOpenButton, 'Ouvrir une vidéo · Ctrl+O', self.choose_video)
        row.addWidget(self.open_button)
        self.pause = self.button(QStyle.StandardPixmap.SP_MediaPlay, 'Lecture / pause · Espace', self.playback.toggle_pause)
        row.addWidget(self.pause)
        self.position = QLabel('0:00 / 0:00')
        row.addWidget(self.position)
        row.addStretch()
        self.mute = self.button(QStyle.StandardPixmap.SP_MediaVolume, 'Muet · M', self.toggle_mute)
        self.mute.setCheckable(True)
        row.addWidget(self.mute)
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(DEFAULT_VOLUME)
        self.volume.setFixedWidth(100)
        self.volume.setAccessibleName('Volume')
        self.volume.valueChanged.connect(self.player.set_volume)
        self.player.set_volume(DEFAULT_VOLUME)
        row.addWidget(self.volume)
        row.addWidget(self.button(QStyle.StandardPixmap.SP_TitleBarMaxButton, 'Plein écran · F', self.fullscreen))
        layout.addLayout(row)

        self.hint = QLabel('Ouvrez une vidéo avec Ctrl+O ou le bouton dossier.', self.screen)
        self.hint.setStyleSheet('color:#aab4c4; background:transparent;')
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(150)
        self.shortcuts = []
        for key, action in [('Ctrl+O', self.choose_video), ('Ctrl+Shift+D', self.quick_vocalize), ('Space', self.playback.toggle_pause),
                            ('Left', lambda: self.playback.skip(-5)), ('Right', lambda: self.playback.skip(5)),
                            ('M', self.toggle_mute), ('F', self.fullscreen),
                            ('Escape', lambda: self.showNormal() if self.isFullScreen() else None)]:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(action)
            self.shortcuts.append(shortcut)
        self.last_state = None

    def control_icon(self, standard):
        # Same icon recoloring as add_dub/gui/preview.py.
        pixmap = self.style().standardIcon(standard).pixmap(QSize(22, 22))
        painter = QPainter(pixmap)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(pixmap.rect(), QColor('#eeeeee'))
        painter.end()
        return QIcon(pixmap)

    def button(self, symbol, label, action):
        button = QToolButton()
        button.setIcon(self.control_icon(symbol))
        button.setIconSize(QSize(22, 22))
        button.setToolTip(label)
        button.setAccessibleName(label)
        button.clicked.connect(action)
        return button

    def choose_video(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Ouvrir une vidéo', '',
                'Vidéos (*.mkv *.mp4 *.avi *.mov *.webm *.m4v *.wmv);;Tous les fichiers (*)')
        if path:
            self.open_video(path)

    def open_video(self, path):
        if not Path(path).is_file():
            QMessageBox.warning(self, APP_NAME, 'Ce fichier est introuvable.')
            return
        try:
            self.playback.open(str(Path(path).resolve()))
            self.hint.hide()
            self.last_state = None
            self.setWindowTitle(Path(path).name + ' — ' + APP_NAME)
        except RuntimeError as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))

    def refresh(self):
        state = self.player.get_state()
        if state == 7 and self.last_state != 7:
            QMessageBox.warning(self, APP_NAME, 'Impossible de lire cette vidéo.')
        self.last_state = state
        symbol = QStyle.StandardPixmap.SP_MediaPause if self.player.is_playing() else QStyle.StandardPixmap.SP_MediaPlay
        self.pause.setIcon(self.control_icon(symbol))
        total = self.player.get_length()
        current = self.player.get_time()
        self.seek.setEnabled(total > 0)
        if not self.seek.isSliderDown() and total > 0:
            self.seek.setValue(round(max(0, current)/total*10000))
        self.position.setText(f'{time_text(current)} / {time_text(total)}')
        # Keep the controls above the engine's native video child.
        self.controls.raise_()

    def toggle_mute(self):
        muted = not self.player.is_muted()
        self.player.set_mute(muted)
        self.mute.setChecked(muted)
        self.mute.setIcon(self.control_icon(QStyle.StandardPixmap.SP_MediaVolumeMuted if muted else QStyle.StandardPixmap.SP_MediaVolume))

    def fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def context_menu(self, point):
        menu = QMenu(self)
        menu.addAction('Ouvrir une vidéo…', self.choose_video)
        menu.addAction('Lecture / pause', self.playback.toggle_pause)
        menu.addAction('Plein écran', self.fullscreen)
        menu.addSeparator()
        self.add_track_menu(menu, 'Pistes audio', self.player.audio_tracks(),
                            self.player.current_audio_track(), self.player.select_audio_track)
        self.add_track_menu(menu, 'Sous-titres', self.player.subtitle_track_descriptions(),
                            self.player.current_subtitle_track(), self.player.select_subtitle_track)
        menu.addSeparator()
        menu.addAction('Vocaliser les sous-titres', self.choose_voice).setEnabled(bool(self.playback.path))
        menu.addAction('Vocaliser avec les réglages enregistrés · Ctrl+Maj+D', self.quick_vocalize).setEnabled(bool(self.playback.path))
        try:
            menu.exec(self.screen.mapToGlobal(point))
        finally:
            menu.deleteLater()

    def add_track_menu(self, menu, title, tracks, current, select):
        submenu = menu.addMenu(title)
        if not any(track_id >= 0 for track_id, _ in tracks):
            submenu.addAction('Aucune piste disponible').setEnabled(False)
            return
        group = QActionGroup(submenu)
        group.setExclusive(True)
        if not any(track_id == -1 for track_id, _ in tracks):
            tracks = [(-1, 'Désactivé')] + tracks
        for track_id, name in tracks:
            action = submenu.addAction('Désactivé' if track_id == -1 else name)
            action.setCheckable(True)
            action.setChecked(track_id == current)
            group.addAction(action)
            action.triggered.connect(lambda checked, chosen=track_id: self.select_track(select, chosen))

    def select_track(self, select, track_id):
        if not select(track_id):
            QMessageBox.warning(self, APP_NAME, 'Impossible de sélectionner cette piste.')

    def choose_voice(self, quick=False):
        if not self.playback.path:
            return
        selected = self.player.current_subtitle_track()
        tracks = self.player.embedded_subtitles()
        ordinal = next((i for i, track in enumerate(tracks) if track['id'] == selected), None)
        if selected < 0:
            QMessageBox.information(self, APP_NAME, 'Sélectionnez d’abord une piste de sous-titres dans le menu.')
            return
        if ordinal is None:
            QMessageBox.warning(self, APP_NAME, 'Cette piste externe n’est pas encore prise en charge pour la vocalisation.')
            return
        settings = self.voice_settings or {'language': self.system_language}
        if quick:
            try:
                settings = load_settings()
                if not settings or not settings.get('voice'):
                    raise ValueError('Choisissez une voix puis cliquez sur « Enregistrer les réglages » dans Vocaliser les sous-titres.')
            except (OSError, ValueError, TypeError) as exc:
                QMessageBox.warning(self, APP_NAME, str(exc))
                return
            self.prepare_audio(ordinal, tracks, settings, auto_restart=True)
            return
        dialog = VoiceDialog(self.tasks, settings, self)
        dialog.settings_saved.connect(lambda value: setattr(self, 'voice_settings', value))
        try:
            if dialog.exec():
                self.voice_settings = dialog.selection()
                self.prepare_audio(ordinal, tracks, self.voice_settings)
        finally:
            dialog.deleteLater()

    def quick_vocalize(self):
        self.choose_voice(quick=True)

    def prepare_audio(self, ordinal, tracks, settings, auto_restart=False):
        self.player.ensure_paused()
        progress = GenerationDialog({'video': self.playback.path,
                    'ordinal': ordinal, 'track_count': len(tracks), 'ff_index': tracks[ordinal]['ff_index'],
                    'audio_ff_index': self.player.selected_audio_ff_index(),
                    'duration_ms': self.player.get_length(), 'settings': settings}, self, auto_restart=auto_restart)
        try:
            progress.exec()
            if progress.output_path and progress.original_path and progress.choice:
                self.player.add_audio_pair(progress.original_path, progress.output_path,
                                           bg_mix=settings.get('bg_mix', 1), tts_mix=settings.get('tts_mix', 1))
                if progress.choice == 'restart':
                    self.player.set_position(0)
                self.player.play_current()
        except RuntimeError as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))
        finally:
            progress.deleteLater()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'controls'):
            self.controls.setGeometry(12, self.screen.height()-96, self.screen.width()-24, 84)
            self.hint.setGeometry(0, self.screen.height()//2-20, self.screen.width(), 40)

    def closeEvent(self, event):
        self.timer.stop()
        self.player.close()
        event.accept()
