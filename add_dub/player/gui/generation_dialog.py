"""Suivi du processus WAV avec la barre du GUI add_dub."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import uuid
from PySide6.QtCore import QProcess, QProcessEnvironment, QTimer
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QProgressBar
from add_dub.player.io.fs import ROOT, WAV_DIR, WORK_ROOT, ensure_base_dirs
from add_dub.progress import PREFIX


class GenerationDialog(QDialog):
    def __init__(self, request, parent=None, auto_restart=False):
        super().__init__(parent)
        self.setWindowTitle('Génération de la piste vocale')
        self.setMinimumWidth(560)
        self.output_path = None
        self.original_path = None
        self.error_text = ''
        self.buffer = ''
        self.log_tail = ''
        self.running = True
        self.cancelled = False
        self.choice = None
        self.auto_restart = auto_restart
        self.stage = 'Préparation'
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(16)
        self.label = QLabel('La vidéo est en pause.')
        self.label.setWordWrap(True)
        layout.addWidget(self.label)
        self.bar = QProgressBar(self)
        self.bar.setRange(0, 1000)
        self.bar.setValue(0)
        self.bar.setFormat('Préparation · 0,0 %')
        self.bar.setStyleSheet('''
            QProgressBar { border: 1px solid #858585; border-radius: 0;
                background-color: #191919; color: #ffffff; min-height: 26px;
                text-align: center; padding: 2px; }
            QProgressBar::chunk { background-color: #176b35; border-radius: 0; }
        ''')
        layout.addWidget(self.bar)
        self.actions = QHBoxLayout()
        self.button = QPushButton('Annuler')
        self.button.clicked.connect(self.reject)
        self.actions.addWidget(self.button)
        self.restart_button = QPushButton('Rejouer')
        self.restart_button.clicked.connect(lambda: self.choose_after_success('restart'))
        self.continue_button = QPushButton('Continuer')
        self.continue_button.clicked.connect(lambda: self.choose_after_success('continue'))
        self.restart_button.hide()
        self.continue_button.hide()
        self.actions.addWidget(self.restart_button)
        self.actions.addWidget(self.continue_button)
        layout.addLayout(self.actions)
        ensure_base_dirs()
        self.work = Path(tempfile.mkdtemp(prefix='tts-', dir=WORK_ROOT))
        request = dict(request)
        request['output'] = str(WAV_DIR / (Path(request['video']).stem + '_' + uuid.uuid4().hex[:12] + '.wav'))
        request['original_output'] = str(WAV_DIR / (Path(request['video']).stem + '_original_ducked_' + uuid.uuid4().hex[:12] + '.wav'))
        self.request_path = self.work / 'request.json'
        self.request_path.write_text(json.dumps(request, ensure_ascii=False), encoding='utf-8')
        self.process = QProcess(self)
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert('ADD_DUB_GUI_PROGRESS', '1')
        environment.insert('ADD_DUB_GUI_WORK_TMP', str(self.work))
        environment.insert('PYTHONIOENCODING', 'utf-8')
        environment.insert('PYTHONUNBUFFERED', '1')
        self.process.setProcessEnvironment(environment)
        self.process.setWorkingDirectory(str(ROOT))
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.finished.connect(self.on_process_finished)
        self.process.errorOccurred.connect(self.process_error)
        self.process.setProgram(sys.executable)
        self.process.setArguments(([] if getattr(sys, 'frozen', False) else ['-u', '-m', 'add_dub'])
                                  + ['--player-generate', str(self.request_path)])
        QTimer.singleShot(0, self.start_process)

    def start_process(self):
        self.process.start()
        self.process.closeWriteChannel()

    def read_output(self):
        # Protocol lines are ASCII JSON (escaped Unicode), so chunks can be
        # decoded independently even if a multibyte log message is split.
        self.buffer += bytes(self.process.readAllStandardOutput()).decode('utf-8', 'replace')
        while '\n' in self.buffer:
            line, self.buffer = self.buffer.split('\n', 1)
            if PREFIX not in line:
                self.log_tail = (self.log_tail + line + '\n')[-3000:]
                continue
            try:
                event = json.loads(line.split(PREFIX, 1)[1])
            except ValueError:
                continue
            kind = event.get('event')
            if kind == 'stage':
                self.stage = event.get('text', 'En cours')
                self.bar.setFormat(self.stage + ' · 0,0 %')
            elif kind == 'progress':
                percent = max(0, min(99.9, float(event['value'])))
                self.bar.setValue(round(percent * 10))
                self.bar.setFormat(f'{self.stage} · {percent:.1f} %'.replace('.', ','))
            elif kind == 'finalizing':
                self.bar.setFormat(self.stage + ' · Finalisation…')
            elif kind == 'complete':
                pass
            elif kind == 'message':
                self.label.setText(event['text'])
            elif kind == 'result':
                self.output_path = event['path']
                self.original_path = event.get('original_path')
                # Le résultat est enregistré ici. Comme dans add_dub, seule
                # la sortie réussie du processus valide la fin du traitement.
            elif kind == 'error':
                self.error_text = event['text']

    def process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.error_text = self.process.errorString()
            self.on_process_finished(1, QProcess.ExitStatus.CrashExit)

    def on_process_finished(self, code, status):
        if not self.running:
            return
        self.read_output()
        if self.cancelled:
            self.running = False
            self.label.setText('Génération annulée. La vidéo reste en pause.')
        elif (code == 0 and status == QProcess.ExitStatus.NormalExit
              and self.output_path and Path(self.output_path).is_file()
              and self.original_path and Path(self.original_path).is_file()):
            self.finish_success()
            return
        else:
            self.running = False
            self.output_path = None
            self.label.setText('Échec de la génération :\n' + (self.error_text or self.log_tail or 'Le processus TTS s’est arrêté.'))
        # Only remove this job's directory under this project's tmp.
        if self.work.resolve().parent == WORK_ROOT.resolve():
            shutil.rmtree(self.work, ignore_errors=True)
        self.button.setText('Fermer')
        self.button.setEnabled(True)

    def finish_success(self):
        if not self.running or not self.output_path:
            return
        self.running = False
        self.bar.setValue(1000)
        self.bar.setFormat('Vocalisation terminée')
        self.label.setText('Vocalisation terminée')
        if self.work.resolve().parent == WORK_ROOT.resolve():
            shutil.rmtree(self.work, ignore_errors=True)
        self.button.hide()
        self.restart_button.show()
        self.continue_button.show()
        self.restart_button.setFocus()
        if self.auto_restart:
            self.choose_after_success('restart')

    def reject(self):
        if not self.running:
            return super().reject()
        if self.cancelled:
            return
        self.cancelled = True
        self.button.setEnabled(False)
        self.label.setText('Arrêt de la génération…')
        # As in add_dub GUI: terminate the whole OneCore worker tree.
        self.stopper = QProcess(self)
        self.stopper.finished.connect(self.cancel_finished)
        self.stopper.start('taskkill', ['/PID', str(self.process.processId()), '/T', '/F'])
        QTimer.singleShot(2500, self.cancel_timeout)

    def cancel_finished(self, code, status):
        if not self.running:
            return
        if code == 0:
            self.finish_cancelled()
        else:
            self.cancelled = False
            self.button.setEnabled(True)
            self.label.setText('L’arrêt a échoué ; la génération continue.')

    def cancel_timeout(self):
        if self.running and self.cancelled:
            self.process.kill()
            self.finish_cancelled()

    def finish_cancelled(self):
        self.running = False
        self.output_path = None
        self.label.setText('Génération annulée. La vidéo reste en pause.')
        if self.work.resolve().parent == WORK_ROOT.resolve():
            shutil.rmtree(self.work, ignore_errors=True)
        self.button.setText('Fermer')
        self.button.setEnabled(True)

    def choose_after_success(self, choice):
        if not self.output_path:
            return
        self.choice = choice
        self.accept()
