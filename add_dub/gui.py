"""Interface Qt accessible : configuration de lots et liste d'attente."""
from __future__ import annotations
import codecs
import os
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    _bundle = Path(sys._MEIPASS)
    for _dll_dir in (_bundle / "PySide6", _bundle / "shiboken6"):
        if _dll_dir.is_dir() and hasattr(os, "add_dll_directory"):
            os.add_dll_directory(str(_dll_dir))

from PySide6.QtCore import Qt, QProcess, QProcessEnvironment, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFileDialog, QTreeWidget, QTreeWidgetItem, QPlainTextEdit,
    QProgressBar, QMessageBox, QComboBox, QDialog, QScrollArea,
)
from add_dub.io import fs
from add_dub.gui_model import FIELDS, BOOLS, batch_command, Job, Settings
from add_dub.gui_widgets import Async
from add_dub.gui_dialog import ConfigureDialog
from add_dub.gui_theme import apply_theme


class Application(QMainWindow):
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
        self.running = False
        self.pending = []
        self.position = 0
        self.failed_jobs = set()
        self.stop_requested = False
        fs.ensure_base_dirs()
        self.setWindowTitle('add_dub — Doublage de sous-titres')
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
        heading = QLabel('add_dub')
        heading.setObjectName('heading')
        layout.addWidget(heading)
        layout.addWidget(QLabel('Des sous-titres à la voix · Vidéo originale conservée'))
        toolbar = QHBoxLayout()
        self.add_files_button = QPushButton('Ajouter des vidéos…')
        self.add_folder_button = QPushButton('Ajouter un dossier…')
        self.add_files_button.clicked.connect(self.add_files)
        self.add_folder_button.clicked.connect(self.add_folder)
        toolbar.addWidget(self.add_files_button)
        toolbar.addWidget(self.add_folder_button)
        toolbar.addStretch()
        toolbar.addWidget(QLabel('Texte'))
        self.scale = QComboBox()
        self.scale.addItems(['100 %', '125 %', '150 %', '200 %'])
        self.scale.setAccessibleName('Taille du texte de l’interface')
        self.scale.currentIndexChanged.connect(lambda index: QApplication.instance().setFont(QFont('Segoe UI', [11, 14, 17, 22][index])))
        toolbar.addWidget(self.scale)
        layout.addLayout(toolbar)
        action_bar = QHBoxLayout()
        self.start_button = QPushButton('Lancer le traitement')
        self.start_button.setObjectName('primary')
        self.start_button.setMinimumHeight(52)
        self.start_button.setMinimumWidth(240)
        self.start_button.clicked.connect(self.start)
        action_bar.addWidget(self.start_button)
        self.stop = QPushButton('Arrêter après cette vidéo')
        self.stop.setEnabled(False)
        self.stop.clicked.connect(self.request_stop)
        action_bar.addWidget(self.stop)
        action_bar.addStretch()
        layout.addLayout(action_bar)
        self.empty = QLabel('La liste d’attente est vide. Ajoutez des vidéos ou un dossier pour choisir les pistes et la voix.')
        self.empty.setWordWrap(True)
        layout.addWidget(self.empty)
        self.queue = QTreeWidget()
        self.queue.setHeaderLabels(['Lot', 'Vidéos', 'État', 'Configuration'])
        self.queue.setAccessibleName('Liste d’attente des doublages')
        self.queue.setRootIsDecorated(False)
        self.queue.setColumnWidth(0, 320)
        self.queue.setColumnWidth(1, 80)
        self.queue.setColumnWidth(2, 210)
        self.queue.setColumnWidth(3, 160)
        self.queue.itemDoubleClicked.connect(lambda item, column: self.edit_job(self.queue.indexOfTopLevelItem(item)))
        layout.addWidget(self.queue, 2)
        self.remove = QPushButton('Retirer le lot sélectionné')
        self.remove.clicked.connect(self.remove_job)
        layout.addWidget(self.remove, alignment=Qt.AlignmentFlag.AlignLeft)
        self.status = QLabel('Prêt.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setAccessibleName('Progression des fichiers de la liste d’attente')
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setAccessibleName('Journal du traitement')
        self.log.setMaximumBlockCount(2500)
        self.log.setMinimumHeight(110)
        layout.addWidget(self.log, 1)
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
                  recursive=self.args.recursive, preserve_tree=self.args.preserve_tree,
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

    def remove_job(self):
        index = self.queue.indexOfTopLevelItem(self.queue.currentItem())
        if not self.running and 0 <= index < len(self.jobs):
            del self.jobs[index]
            self.refresh()

    def refresh(self):
        index = self.queue.indexOfTopLevelItem(self.queue.currentItem())
        self.queue.clear()
        for number, job in enumerate(self.jobs):
            names = ', '.join(Path(p).name or p for p in job.sources)
            item = QTreeWidgetItem(self.queue, [names, str(len(job.selected)), job.status, ''])
            item.setToolTip(0, '\n'.join(job.sources))
            button = QPushButton('⚙ Modifier')
            button.setAccessibleName(f'Modifier les réglages du lot {number + 1} : {names}')
            button.setEnabled(not self.running)
            button.clicked.connect(lambda checked=False, i=number: self.edit_job(i))
            self.queue.setItemWidget(item, 3, button)
        if 0 <= index < len(self.jobs):
            self.queue.setCurrentItem(self.queue.topLevelItem(index))
        self.empty.setVisible(not self.jobs)
        self.start_button.setEnabled(not self.running and any(j.status != 'Terminé' for j in self.jobs))
        self.remove.setEnabled(not self.running and bool(self.jobs))
        self.add_files_button.setEnabled(not self.running)
        self.add_folder_button.setEnabled(not self.running)
        self.stop.setEnabled(self.running and not self.stop_requested)

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
        if not self.pending:
            return
        self.running = True
        self.position = 0
        self.failed_jobs = set()
        self.stop_requested = False
        self.progress.setRange(0, len(self.pending))
        self.progress.setValue(0)
        self.refresh()
        self.next_file()

    def next_file(self):
        if self.stop_requested or self.position >= len(self.pending):
            self.running = False
            if self.stop_requested:
                self.status.setText('Arrêt effectué après la vidéo. Relancez pour poursuivre la liste.')
            else:
                self.status.setText('Liste terminée avec des erreurs : consultez le journal.' if self.failed_jobs else 'Tous les traitements sont terminés.')
            for job in self.jobs:
                if job.status.startswith('En cours'):
                    job.status = 'En attente'
            self.refresh()
            return
        index, video, command = self.pending[self.position]
        self.jobs[index].status = f'En cours — {Path(video.path).name}'
        self.status.setText(f'Vidéo {self.position + 1} / {len(self.pending)} — {Path(video.path).name}')
        self.log.appendPlainText(f'\n── {video.path} ──')
        self.decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
        self.file_finished = False
        environment = QProcessEnvironment.systemEnvironment()
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
        text = self.decoder.decode(bytes(self.process.readAllStandardOutput()))
        if text:
            self.log.moveCursor(self.log.textCursor().MoveOperation.End)
            self.log.insertPlainText(text.replace('\r', '\n'))
            self.log.ensureCursorVisible()

    def process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.log.appendPlainText('Lancement impossible : ' + self.process.errorString())
            self.finished_file(1, QProcess.ExitStatus.CrashExit)

    def finished_file(self, code, exit_status):
        if not self.running or self.file_finished:
            return
        self.file_finished = True
        self.read_output()
        tail = self.decoder.decode(b'', final=True)
        if tail:
            self.log.insertPlainText(tail)
        index, video, command = self.pending[self.position]
        job = self.jobs[index]
        if code == 0 and exit_status == QProcess.ExitStatus.NormalExit:
            job.completed.add(video.path)
        else:
            self.failed_jobs.add(index)
            self.log.appendPlainText(f'Échec de {Path(video.path).name} (code {code}).')
        self.position += 1
        self.progress.setValue(self.position)
        more_for_job = any(i == index for i, _, _ in self.pending[self.position:])
        job.status = 'En attente' if more_for_job else 'Erreur — relancer ou modifier' if index in self.failed_jobs else 'Terminé'
        self.refresh()
        QTimer.singleShot(0, self.next_file)

    def request_stop(self):
        self.stop_requested = True
        self.stop.setEnabled(False)
        self.status.setText('Arrêt demandé : la vidéo en cours sera terminée avant la pause.')

    def closeEvent(self, event):
        if self.running:
            QMessageBox.information(self, 'Traitement en cours', 'Utilisez « Arrêter après cette vidéo », puis fermez la fenêtre lorsque le traitement est arrêté.')
            event.ignore()
        else:
            event.accept()


def main(args) -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    apply_theme(app)
    window = Application(args)
    window.showMaximized()
    return app.exec()
