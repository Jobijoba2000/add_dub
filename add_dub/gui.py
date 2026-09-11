"""Interface Qt accessible : configuration de lots et liste d'attente."""
from __future__ import annotations
from collections import deque
import codecs
import json
import time
import os
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    _bundle = Path(sys._MEIPASS)
    for _dll_dir in (_bundle / "PySide6", _bundle / "shiboken6"):
        if _dll_dir.is_dir() and hasattr(os, "add_dll_directory"):
            os.add_dll_directory(str(_dll_dir))

from PySide6.QtCore import Qt, QProcess, QProcessEnvironment, QTimer, QSize, QFileInfo
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFileDialog, QTreeWidget, QTreeWidgetItem,
    QProgressBar, QMessageBox, QDialog, QScrollArea, QFileIconProvider, QToolButton, QMenu, QStyle, QHeaderView, QStackedWidget, QTabBar,
)
from add_dub.io import fs
from add_dub.gui_model import FIELDS, BOOLS, batch_command, Job, Settings
from add_dub.gui_widgets import Async, SmoothTreeWidget, SpacedMenu, QueueTabBar
from add_dub.gui_run import VideoRunFiles, partition_existing
from add_dub.progress import PREFIX, VideoProgress, aggregate, remaining_seconds
from add_dub.gui_dialog import ConfigureDialog, yellow_folder_icon
from add_dub.gui_theme import apply_theme, playback_icon, video_file_icon, settings_icon, icons8_icon


from add_dub.gui_titlebar import CaptionWindow


class Application(CaptionWindow):
    def __init__(self, args):
        super().__init__()
        self.args = args
        self.jobs = []
        self.tasks = Async(self)
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.finished.connect(self.finished_file)
        self.process.errorOccurred.connect(self.process_error)
        self.stopper = QProcess(self)
        self.stopper.finished.connect(self.stopper_finished)
        self.stopper.errorOccurred.connect(self.stopper_error)
        self.process.started.connect(self.process_started)
        self.run_files = None
        self.cancel_cleanup_attempts = 0
        self.running = False
        self.pending = []
        self.position = 0
        self.failed_jobs = set()
        self.stop_requested = False
        self.video_states = {}
        self.video_errors = {}
        self.rows = {}
        self.full_paths = False
        self.active_key = None
        self.active_bar = None
        self.video_progress = VideoProgress()
        self.started_at = None
        self.elapsed = 0
        self.durations = []
        self.clock_timer = QTimer(self)
        self.clock_timer.setInterval(1000)
        self.clock_timer.timeout.connect(self.update_totals)
        fs.ensure_base_dirs()
        self.setWindowTitle('add_dub')
        resource_root = Path(sys._MEIPASS) if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1]
        self.setWindowIcon(QIcon(str(resource_root / 'docs' / 'add_dub.ico')))
        self.install_caption()
        self.resize(1100, 780)
        self.setMinimumSize(760, 540)
        central = QWidget()
        central.setMinimumWidth(720)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(central)
        self.setCentralWidget(scroll)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(18)
        toolbar = QHBoxLayout()
        self.open_button = QToolButton()
        self.open_button.setObjectName('openSources')
        self.open_button.setText('Ouvrir')
        self.open_button.setIcon(yellow_folder_icon(True))
        self.open_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = SpacedMenu(self.open_button)
        self.open_video_action = menu.addAction(video_file_icon(), 'Ouvrir des vidéos…', self.add_files)
        self.open_folder_action = menu.addAction(yellow_folder_icon(False), 'Ouvrir un dossier…', self.add_folder)
        self.open_button.setMenu(menu)
        self.settings_button = QToolButton()
        self.settings_button.setText('Paramètres')
        self.settings_button.setIcon(settings_icon())
        self.settings_button.setToolTip('Options globales — à venir')
        self.settings_button.setEnabled(False)
        for button in (self.open_button, self.settings_button):
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            button.setIconSize(QSize(48, 48))
            button.setMinimumSize(115, 92)
            toolbar.addWidget(button)
        self.start_button = QToolButton()
        self.start_button.setObjectName('playback')
        self.start_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.start_button.setIconSize(QSize(48, 48))
        self.start_button.setMinimumSize(130, 92)
        self.play_icon = playback_icon(False)
        self.stop_icon = playback_icon(True)
        self.start_button.clicked.connect(self.toggle_processing)
        toolbar.addWidget(self.start_button)
        toolbar.addStretch()
        layout.addLayout(toolbar)
        self.empty = QLabel('La liste d’attente est vide. Ajoutez des vidéos ou un dossier pour choisir les pistes et la voix.')
        self.empty.setWordWrap(True)
        self.info_panel = QWidget()
        info_layout = QHBoxLayout(self.info_panel)
        info_layout.setContentsMargins(0, 10, 0, 10)
        info_layout.setSpacing(12)
        info_icon = QLabel()
        info_source = icons8_icon('info')
        info_icon.setPixmap((info_source if not info_source.isNull()
                             else self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation)).pixmap(36, 36))
        info_icon.setFixedSize(36, 36)
        info_icon.setAccessibleName('Information')
        info_layout.addWidget(info_icon, alignment=Qt.AlignmentFlag.AlignVCenter)
        info_layout.addWidget(self.empty, 1)
        self.info_panel.setMinimumHeight(64)
        layout.addWidget(self.info_panel)
        queue_layout = QVBoxLayout()
        queue_layout.setSpacing(0)
        self.queue_tabs = QueueTabBar()
        self.queue_tabs.setObjectName('queueTabs')
        self.queue_tabs.setAccessibleName('Vues de la file d’attente')
        self.queue_tabs.setExpanding(False)
        self.queue_tabs.setDrawBase(False)
        self.queue_tabs.addTab('En attente (0)')
        self.queue_tabs.addTab('Terminé (0)')
        queue_layout.addWidget(self.queue_tabs)
        self.queue_stack = QStackedWidget()
        self.queue = SmoothTreeWidget()
        self.finished_queue = SmoothTreeWidget()
        for tree, name in ((self.queue, 'Vidéos en attente'),
                           (self.finished_queue, 'Vidéos terminées')):
            tree.setHeaderLabels(['Vidéo', 'Dossier de destination', 'Statut'])
            tree.setObjectName('queueList')
            tree.setIconSize(QSize(28, 28))
            tree.setMouseTracking(True)
            tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            tree.customContextMenuRequested.connect(lambda point, tree=tree: self.queue_menu(tree, point))
            tree.setAccessibleName(name)
            tree.setRootIsDecorated(False)
            tree.setUniformRowHeights(False)
            tree.header().setMinimumSectionSize(100)
            tree.header().setStretchLastSection(True)
            tree.header().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            for column, width in enumerate((460, 380, 330)):
                tree.setColumnWidth(column, width)
            self.queue_stack.addWidget(tree)
        self.queue_tabs.currentChanged.connect(self.switch_queue)
        # Les deux listes gardent les mêmes séparations de colonnes.
        self.queue.header().sectionResized.connect(
            lambda col, old, size: self.finished_queue.setColumnWidth(col, size))
        self.finished_queue.header().sectionResized.connect(
            lambda col, old, size: self.queue.setColumnWidth(col, size))
        queue_layout.addWidget(self.queue_stack, 1)
        layout.addLayout(queue_layout, 1)
        self.status = QLabel('Prêt.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setAccessibleName('Progression des fichiers de la liste d’attente')
        self.progress.setRange(0, 1000)
        self.progress.setFormat('0,0 %')
        self.progress.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress.setValue(0)
        totals = QHBoxLayout()
        totals.addWidget(self.progress, 1)
        self.time_label = QLabel('Écoulé : 00:00:00\nRestant estimé : —')
        totals.addWidget(self.time_label)
        layout.addLayout(totals)
        self.log_lines = deque(maxlen=2500)
        self.refresh()
        if args.input:
            QTimer.singleShot(0, lambda: self.configure_sources(args.input))

    def add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, 'Ajouter des vidéos', fs.INPUT_DIR, 'Vidéos (*.mkv *.mp4 *.avi *.mov)')
        if paths:
            self.configure_sources(paths)

    def add_folder(self):
        path = QFileDialog.getExistingDirectory(self, 'Ajouter un dossier', fs.INPUT_DIR)
        if path:
            self.configure_sources([path])

    def configure_sources(self, paths):
        if self.running:
            return
        job = Job([os.path.abspath(p) for p in paths], Settings.from_args(self.args),
                  os.path.abspath(self.args.output_dir or fs.OUTPUT_DIR),
                  recursive=True, preserve_tree=True,
                  resume=not self.args.overwrite, dry_run=self.args.dry_run)
        dialog = ConfigureDialog(job, self.tasks, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.jobs.append(dialog.job)
            self.refresh()
        dialog.deleteLater()

    def edit_job(self, index):
        if self.running or not 0 <= index < len(self.jobs):
            return
        dialog = ConfigureDialog(self.jobs[index], self.tasks, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.jobs[index] = dialog.job
            self.refresh()
        dialog.deleteLater()

    def queue_menu(self, tree, point):
        item = tree.itemAt(point)
        if item is not None:
            tree.setCurrentItem(item)
        key = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        menu = self.make_queue_menu(key)
        menu.exec(tree.viewport().mapToGlobal(point))
        menu.deleteLater()

    def make_queue_menu(self, key):
        menu = QMenu(self)
        paths = menu.addAction('Afficher les noms seuls' if self.full_paths else 'Afficher les chemins complets')
        paths.triggered.connect(lambda: self.set_full_paths(not self.full_paths))
        menu.addSeparator()
        stop = menu.addAction(self.stop_icon, 'Arrêter le traitement', self.request_stop)
        stop.setEnabled(self.running and not self.stop_requested)
        menu.addSeparator()
        for label, scope, enabled in (
                ('Retirer ce fichier de la liste', key, key in self.rows),
                ('Retirer les fichiers terminés de la liste', 'completed',
                 any(v.path in j.completed for j in self.jobs for v in j.selected)),
                ('Vider toute la file d’attente', 'all', bool(self.rows))):
            action = menu.addAction(label)
            action.setEnabled(enabled and not self.running)
            action.setToolTip('Arrêtez le traitement pour modifier la liste.' if self.running
                              else 'Retire uniquement les entrées de la liste, sans effacer les fichiers.')
            action.triggered.connect(lambda checked=False, scope=scope: self.remove_entries(scope))
        menu.setToolTipsVisible(True)
        return menu

    def set_full_paths(self, enabled):
        self.full_paths = enabled
        for tree in (self.queue, self.finished_queue):
            tree.headerItem().setText(0, 'Vidéo — chemin source' if enabled else 'Vidéo')
        self.refresh()

    def remove_entries(self, scope):
        if self.running:
            return
        for index, job in enumerate(self.jobs):
            for video in job.videos:
                key = (index, video.path)
                if (scope == 'all' or scope == key
                        or scope == 'completed' and video.path in job.completed):
                    video.selected = False
        self.refresh()

    def refresh(self):
        desired = {}
        for number, job in enumerate(self.jobs):
            for video in job.selected:
                desired[(number, video.path)] = (job, video)
        active = self.active_key if self.running and not getattr(self, 'file_finished', True) else None
        # Retirer seulement la barre dont le traitement vient de finir.
        old_key = getattr(self, 'active_bar_key', None)
        if old_key != active and self.active_bar is not None:
            old_item = self.rows.get(old_key)
            if old_item and old_item.treeWidget():
                old_item.treeWidget().removeItemWidget(old_item, 2)
                old_item.setSizeHint(2, QSize())
            self.active_bar = None
        self.active_bar_key = active
        for key in list(self.rows):
            if key not in desired:
                item = self.rows.pop(key)
                tree = item.treeWidget()
                tree.takeTopLevelItem(tree.indexOfTopLevelItem(item))
        for key, (job, video) in desired.items():
            state = 'Terminé' if video.path in job.completed else self.video_states.get(key, 'En attente')
            tree = self.finished_queue if video.path in job.completed else self.queue
            item = self.rows.get(key)
            if item is None:
                item = QTreeWidgetItem()
                item.setIcon(0, video_file_icon())
                item.setIcon(1, yellow_folder_icon(False))
                item.setData(0, Qt.ItemDataRole.UserRole, key)
                self.rows[key] = item
                tree.addTopLevelItem(item)
            elif item.treeWidget() is not tree:
                previous = item.treeWidget()
                previous.takeTopLevelItem(previous.indexOfTopLevelItem(item))
                tree.addTopLevelItem(item)
            source = video.path if self.full_paths else Path(video.path).name
            destination = job.output_for(video)
            if not self.full_paths:
                destination = Path(destination).name or destination
            destination = destination.rstrip('/\\') + '\\'
            for column, text in enumerate((source, destination, state)):
                if item.text(column) != text:
                    item.setText(column, text)
            item.setToolTip(0, video.path)
            item.setToolTip(1, job.output_for(video))
            item.setToolTip(2, self.video_errors.get(key, ''))
            if key == active:
                if tree.indexOfTopLevelItem(item) != 0:
                    tree.takeTopLevelItem(tree.indexOfTopLevelItem(item))
                    tree.insertTopLevelItem(0, item)
                if self.active_bar is None:
                    item.setSizeHint(2, QSize(330, 32))
                    self.active_bar = QProgressBar()
                    self.active_bar.setRange(0, 1000)
                    self.active_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    tree.setItemWidget(item, 2, self.active_bar)
                self.update_video_bar()
        if active and active != old_key:
            self.queue.scrollToTop()
        self.queue_tabs.setTabText(0, f'En attente ({self.queue.topLevelItemCount()})')
        self.queue_tabs.setTabText(1, f'Terminé ({self.finished_queue.topLevelItemCount()})')
        self.update_queue_info()
        self.update_playback_button()
        self.open_button.setEnabled(not self.running)

    def switch_queue(self, index):
        self.queue_stack.setCurrentIndex(index)

    def update_queue_info(self):
        remaining = sum(v.path not in j.completed for j in self.jobs for v in j.selected)
        completed = sum(v.path in j.completed for j in self.jobs for v in j.selected)
        videos = f'{remaining} vidéo' + ('s' if remaining != 1 else '')
        if self.running and self.stop_requested:
            message = 'Arrêt en cours : les fichiers provisoires sont en cours de nettoyage.'
        elif self.running:
            message = f'Traitement en cours : {videos} à terminer. Vous pouvez interrompre le traitement avec « Arrêter ».'
        elif remaining:
            errors = any((i, v.path) in self.video_errors for i, j in enumerate(self.jobs)
                         for v in j.selected if v.path not in j.completed)
            if errors:
                message = f'{videos} à traiter, dont des vidéos en erreur. Consultez leur statut, puis cliquez sur « Démarrer » pour réessayer.'
            else:
                message = f'{videos} en attente. Cliquez sur « Démarrer » pour lancer le traitement.'
        elif completed:
            count = f'{completed} vidéo' + ('s terminées' if completed != 1 else ' terminée')
            message = f'Traitement terminé : {count}. Consultez l’onglet « Terminé » ou ajoutez de nouvelles vidéos avec « Ouvrir ».'
        else:
            message = 'La liste d’attente est vide. Utilisez « Ouvrir » pour ajouter des vidéos ou un dossier et choisir les pistes et la voix.'
        self.empty.setText(message)

    def update_video_bar(self):
        if self.active_bar:
            value = self.video_progress.percent
            self.active_bar.setValue(round(value * 10))
            self.active_bar.setFormat(f'{self.video_progress.label} · {value:.1f} %'.replace('.', ','))
            self.active_bar.setAccessibleName(self.active_bar.format())

    def update_totals(self):
        if self.started_at is not None and self.running:
            self.elapsed = time.monotonic() - self.started_at
        value = aggregate(self.position, len(self.pending), self.video_progress.percent if self.active_key else 0)
        self.progress.setValue(round(value * 10))
        self.progress.setFormat(f'{value:.1f} %'.replace('.', ','))
        def duration(seconds):
            seconds = int(seconds)
            return f'{seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}'
        remaining = remaining_seconds(self.durations, len(self.pending) - self.position,
                                      self.video_progress.percent if self.active_key else 0)
        estimate = duration(remaining) if remaining is not None and self.running else '—'
        self.time_label.setText(f'Écoulé : {duration(self.elapsed)}\nRestant estimé : {estimate}')

    def update_playback_button(self):
        ready = any(j.status != 'Terminé' and any(v.path not in j.completed for v in j.selected)
                    for j in self.jobs)
        button = self.start_button
        button.setProperty('processing', self.running)
        button.setIcon(self.stop_icon if self.running else self.play_icon)
        label = ('Arrêt…' if self.stop_requested else 'Arrêter') if self.running else 'Démarrer'
        button.setText(label)
        button.setAccessibleName(label)
        button.setToolTip('Interrompt la vidéo en cours et supprime ses fichiers provisoires.' if self.running else 'Traiter les vidéos sélectionnées restantes.')
        button.setEnabled(not self.stop_requested if self.running else ready)
        button.style().unpolish(button)
        button.style().polish(button)
        button.update()

    def toggle_processing(self):
        if self.running:
            if not self.stop_requested:
                self.request_stop()
        else:
            self.start()

    def start(self):
        if self.running:
            return
        self.pending = []
        try:
            for index, job in enumerate(self.jobs):
                if job.status != 'Terminé':
                    for video, command in job.commands():
                        if video.path not in job.completed:
                            self.pending.append((index, video, command))
        except ValueError as exc:
            QMessageBox.warning(self, 'Liste à vérifier', str(exc))
            return
        self.pending, skipped = partition_existing(self.pending)
        for index, video, _ in skipped:
            self.jobs[index].completed.add(video.path)
        for job in self.jobs:
            if job.selected and all(v.path in job.completed for v in job.selected):
                job.status = 'Terminé'
        if not self.pending:
            self.position = 0
            self.durations = []
            self.elapsed = 0
            self.started_at = None
            self.active_key = None
            self.update_totals()
            self.status.setText('Toutes les vidéos sont déjà terminées ; aucun traitement à lancer.')
            self.refresh()
            return
        self.running = True
        self.position = 0
        self.failed_jobs = set()
        self.stop_requested = False
        self.started_at = time.monotonic()
        self.elapsed = 0
        self.durations = []
        self.active_key = None
        self.clock_timer.start()
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.update_totals()
        self.refresh()
        self.next_file()

    def next_file(self):
        if self.stop_requested or self.position >= len(self.pending):
            self.update_totals()
            self.running = False
            self.active_key = None
            self.clock_timer.stop()
            self.update_totals()
            if self.stop_requested:
                self.status.setText('Traitement arrêté. La vidéo interrompue reste à traiter.')
            else:
                self.status.setText('Liste terminée avec des erreurs : consultez les vidéos signalées en erreur.' if self.failed_jobs else 'Tous les traitements sont terminés.')
            for job in self.jobs:
                if job.status.startswith('En cours'):
                    job.status = 'En attente'
            self.refresh()
            return
        index, video, command = self.pending[self.position]
        self.active_key = (index, video.path)
        self.video_progress = VideoProgress()
        self.file_started_at = time.monotonic()
        self.file_skipped = False
        self.output_buffer = ''
        self.log_lines.clear()
        self.jobs[index].status = f'En cours — {Path(video.path).name}'
        self.status.setText(f'Vidéo {self.position + 1} / {len(self.pending)} — {Path(video.path).name}')
        self.log_lines.append(f'\n── {video.path} ──')
        self.decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
        self.file_finished = False
        try:
            self.run_files = VideoRunFiles(fs.TMP_DIR, self.jobs[index].output_for(video))
        except OSError as exc:
            self.log_lines.append(str(exc))
            self.finished_file(1, QProcess.ExitStatus.CrashExit)
            return
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert('ADD_DUB_GUI_WORK_TMP', str(self.run_files.work))
        environment.insert('ADD_DUB_GUI_PARTIAL_OUTPUT', str(self.run_files.partial))
        environment.insert('TEMP', str(self.run_files.work))
        environment.insert('TMP', str(self.run_files.work))
        environment.insert('ADD_DUB_GUI_PROGRESS', '1')
        environment.insert('PYTHONIOENCODING', 'utf-8')
        environment.insert('PYTHONUNBUFFERED', '1')
        environment.insert('ADD_DUB_OPTIONS', os.path.abspath(os.getenv('ADD_DUB_OPTIONS', 'options.conf')))
        self.process.setProcessEnvironment(environment)
        self.process.setWorkingDirectory(fs.ROOT)
        self.process.setProgram(command[0])
        self.process.setArguments(command[1:])
        self.refresh()
        self.process.start()
        self.process.closeWriteChannel()

    def read_output(self):
        self.consume_output(self.decoder.decode(bytes(self.process.readAllStandardOutput())))

    def consume_output(self, text, final=False):
        self.output_buffer += text.replace('\r', '\n')
        lines = self.output_buffer.split('\n')
        self.output_buffer = lines.pop()
        if final and self.output_buffer:
            lines.append(self.output_buffer)
            self.output_buffer = ''
        for line in lines:
            if line.startswith(PREFIX):
                try:
                    event = json.loads(line[len(PREFIX):])
                    if isinstance(event, dict):
                        if event.get('event') == 'existing_output':
                            self.file_skipped = True
                        self.video_progress.update(event)
                        self.update_video_bar()
                        self.update_totals()
                except (ValueError, TypeError):
                    self.log_lines.append(line)
            elif line.strip():
                self.log_lines.append(line)

    def process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.log_lines.append('Lancement impossible : ' + self.process.errorString())
            self.finished_file(1, QProcess.ExitStatus.CrashExit)

    def finished_file(self, code, exit_status):
        if not self.running or self.file_finished:
            return
        if self.stop_requested:
            self.finish_cancel()
            return
        self.file_finished = True
        self.read_output()
        tail = self.decoder.decode(b'', final=True)
        self.consume_output(tail, final=True)
        index, video, command = self.pending[self.position]
        job = self.jobs[index]
        try:
            if self.run_files:
                if code == 0 and exit_status == QProcess.ExitStatus.NormalExit:
                    self.run_files.publish()
                self.run_files.cleanup()
                self.run_files = None
        except (OSError, ValueError, RuntimeError) as exc:
            code = 1
            self.log_lines.append(f'Erreur de finalisation : {exc}')
        if code == 0 and exit_status == QProcess.ExitStatus.NormalExit:
            job.completed.add(video.path)
        else:
            self.failed_jobs.add(index)
            self.log_lines.append(f'Échec de {Path(video.path).name} (code {code}).')
            self.video_errors[(index, video.path)] = '\n'.join(list(self.log_lines)[-25:])
        self.video_states[(index, video.path)] = 'Terminé' if video.path in job.completed else 'Erreur'
        if (code == 0 and exit_status == QProcess.ExitStatus.NormalExit
                and not self.file_skipped and not getattr(job, 'dry_run', False)):
            self.durations.append(time.monotonic() - self.file_started_at)
        self.position += 1
        self.active_key = None
        self.update_totals()
        more_for_job = any(i == index for i, _, _ in self.pending[self.position:])
        job.status = 'En attente' if more_for_job else 'Erreur — relancer ou modifier' if index in self.failed_jobs else 'Terminé'
        self.refresh()
        QTimer.singleShot(0, self.next_file)

    def request_stop(self):
        if not self.running or self.stop_requested:
            return
        self.stop_requested = True
        self.update_queue_info()
        self.cancel_cleanup_attempts = 0
        self.update_playback_button()
        self.status.setText('Interruption et nettoyage des fichiers provisoires…')
        self.process_started()

    def process_started(self):
        if not self.stop_requested:
            return
        if self.process.state() == QProcess.ProcessState.Starting:
            return  # Le signal started relancera l’interruption avec le PID réel.
        if self.process.state() == QProcess.ProcessState.NotRunning:
            self.finish_cancel()
            return
        if self.stopper.state() != QProcess.ProcessState.NotRunning:
            return
        if os.name == 'nt':
            # Terminer immédiatement le processus surveillé par Qt, puis
            # demander à Windows de rabattre les éventuels enfants restants.
            # Le kill direct évite le délai/race de taskkill sur les petits
            # scripts et garantit que l'interface sort aussitôt de l'état actif.
            pid = self.process.processId()
            self.process.kill()
            if self.process.state() != QProcess.ProcessState.NotRunning and pid:
                self.stopper.start('taskkill', ['/PID', str(pid), '/T', '/F'])
        else:
            self.process.kill()

    def stopper_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.status.setText('Interruption impossible : ' + self.stopper.errorString())
            self.stop_requested = False
            self.update_playback_button()

    def stopper_finished(self, code, status):
        if not self.stop_requested:
            return
        if code != 0 and self.process.state() != QProcess.ProcessState.NotRunning:
            # taskkill peut terminer avant que Windows ne fasse remonter la
            # fermeture du processus Qt. Réessayer brièvement évite de
            # laisser l'interface bloquée sur « interruption impossible ».
            self.cancel_cleanup_attempts += 1
            if self.cancel_cleanup_attempts < 10:
                QTimer.singleShot(100, self.process_started)
                return
            self.status.setText('Interruption impossible : réessayez Arrêter.')
            self.stop_requested = False
            self.update_playback_button()
            return
        self.finish_cancel()

    def finish_cancel(self):
        if not self.running or not self.stop_requested:
            return
        if self.process.state() != QProcess.ProcessState.NotRunning or self.stopper.state() != QProcess.ProcessState.NotRunning:
            return
        try:
            if self.run_files:
                self.run_files.cleanup()
                self.run_files = None
        except (OSError, RuntimeError) as exc:
            self.cancel_cleanup_attempts += 1
            if self.cancel_cleanup_attempts < 15:
                QTimer.singleShot(200, self.finish_cancel)
                return
            self.status.setText(f'Traitement arrêté, nettoyage incomplet : {exc}')
        else:
            self.status.setText('Traitement arrêté. Fichiers provisoires supprimés ; la vidéo reste à traiter.')
        if self.active_key:
            index, path = self.active_key
            self.jobs[index].status = 'En attente'
            self.video_states[self.active_key] = 'En attente'
        self.file_finished = True
        self.update_totals()
        self.running = False
        self.active_key = None
        self.clock_timer.stop()
        self.pending = []
        self.position = 0
        self.durations = []
        self.video_progress = VideoProgress()
        self.update_totals()
        self.refresh()

    def closeEvent(self, event):
        if self.running:
            QMessageBox.information(self, 'Traitement en cours', 'Utilisez « Arrêter », puis fermez la fenêtre lorsque le nettoyage est terminé.')
            event.ignore()
        else:
            event.accept()


def main(args) -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    apply_theme(app)
    window = Application(args)
    window.showMaximized()
    return app.exec()
