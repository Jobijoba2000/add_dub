# add_dub/gui/qt_app.py
from __future__ import annotations

import os
import sys
from typing import List, Dict, Optional, Any

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QPoint, QMutex, QWaitCondition
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QProgressBar,
    QFileDialog,
    QMenu,
    QTabWidget,
    QFrame,
    QMessageBox,
    QAbstractItemView,
)

import add_dub.io.fs as io_fs
from add_dub.core.options import DubOptions
from add_dub.core.services import Services
from add_dub.core.pipeline import process_one_video, _dub_code_from_voice
from add_dub.core.subtitles import resolve_srt_for_video
from add_dub.core.tts_generate import generate_dub_audio
from add_dub.core.codecs import final_audio_codec_args, subtitle_codec_for_container
from add_dub.core.tts_registry import normalize_engine, resolve_voice_with_fallbacks
from add_dub.core.ui import UIInterface
from add_dub.config.effective import effective_values
from add_dub.i18n import init_language

from add_dub.gui.qt_importer import BatchImportDialog
from add_dub.gui.qt_dialogs import ConflictDialog, DefaultSettingsDialog

VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".mov", ".ts", ".m4v", ".webm", ".flv"}


class QtUIAdapter(UIInterface):
    def __init__(self, thread: PipelineWorkerThread, file_index: int):
        self.thread = thread
        self.file_index = file_index

    def message(self, text: str) -> None:
        clean = str(text).strip()
        if clean:
            self.thread.step_progress.emit(self.file_index, clean)

    def error(self, text: str) -> None:
        clean = str(text).strip()
        if clean:
            self.thread.file_error.emit(self.file_index, clean)

    def progress(self, percent: float) -> None:
        pct = int(max(0.0, min(100.0, float(percent))))
        self.thread.pct_progress.emit(self.file_index, pct)

    def ask_yes_no(self, question: str, default: bool = False) -> bool:
        return default

    def ask_float(self, prompt: str, default: float) -> float:
        return float(default)


class PipelineWorkerThread(QThread):
    file_started = pyqtSignal(int, str, dict)
    step_progress = pyqtSignal(int, str)
    pct_progress = pyqtSignal(int, int)
    file_finished = pyqtSignal(int, str, str)
    file_skipped = pyqtSignal(int, str, str)
    file_error = pyqtSignal(int, str)
    global_progress = pyqtSignal(int, str)
    ask_conflict = pyqtSignal(str, str)
    all_finished = pyqtSignal()

    def __init__(self, queue_items: List[Dict[str, Any]], base_settings: Dict[str, Any]):
        super().__init__()
        self.queue_items = queue_items
        self.base_settings = base_settings
        self.should_stop = False
        self.is_paused = False
        self.conflict_response = "yes"
        self.conflict_mutex = QMutex()
        self.conflict_condition = QWaitCondition()

        self.session_overwrite_all = False
        self.session_skip_all = False

    def set_conflict_response(self, resp: str):
        self.conflict_mutex.lock()
        self.conflict_response = resp
        if resp == "yes_all":
            self.session_overwrite_all = True
        elif resp == "no_all":
            self.session_skip_all = True
        self.conflict_condition.wakeAll()
        self.conflict_mutex.unlock()

    def stop_or_pause(self):
        self.should_stop = True
        self.is_paused = True

    def run(self):
        current_idx = 0
        total_files = len(self.queue_items)

        while current_idx < len(self.queue_items):
            if self.should_stop or self.is_paused:
                break

            item = self.queue_items[current_idx]
            video_path = item["path"]
            file_name = os.path.basename(video_path)
            item_settings = item.get("settings", self.base_settings)

            out_dir = str(item_settings.get("output_dir", self.base_settings.get("output_dir", ""))).strip() or io_fs.OUTPUT_DIR
            os.makedirs(out_dir, exist_ok=True)

            self.file_started.emit(current_idx, file_name, item)
            current_global_pct = int(current_idx * 100 / max(1, total_files))
            self.global_progress.emit(current_global_pct, f"Traitement de {current_idx + 1}/{total_files} : {file_name}")

            engine = normalize_engine(item_settings.get("tts_engine", "onecore"))
            voice_id = item_settings.get("voice_id")
            preferred_lang = item_settings.get("voice_lang", "fr-FR")
            resolved = resolve_voice_with_fallbacks(
                engine=engine,
                desired_voice_id=voice_id,
                preferred_lang_base=preferred_lang[:2] if preferred_lang else None,
            )
            if resolved:
                voice_id = resolved["id"] if isinstance(resolved, dict) else resolved

            dub_code = _dub_code_from_voice(voice_id)
            base, _ = os.path.splitext(file_name)
            final_video = io_fs.join_output(f"{base} [dub-{dub_code}].mkv", out_dir)

            overwrite_this = self.session_overwrite_all or bool(item_settings.get("overwrite", False))

            if os.path.exists(final_video) and not self.session_overwrite_all:
                if self.session_skip_all:
                    self.file_skipped.emit(current_idx, video_path, "Fichier déjà existant")
                    current_idx += 1
                    continue

                self.conflict_mutex.lock()
                self.ask_conflict.emit(file_name, final_video)
                self.conflict_condition.wait(self.conflict_mutex)
                user_choice = self.conflict_response
                self.conflict_mutex.unlock()

                if user_choice in ("no", "no_all"):
                    self.file_skipped.emit(current_idx, video_path, "Fichier déjà existant (Ignoré)")
                    current_idx += 1
                    continue
                elif user_choice in ("yes", "yes_all"):
                    overwrite_this = True

            aud_idx = item_settings.get("audio_ffmpeg_index")
            sub_choice = item_settings.get("sub_choice")
            codec = str(item_settings.get("audio_codec", "ac3")).lower()
            raw_br = str(item_settings.get("audio_bitrate", "256")).replace("k", "").strip()
            try:
                bitrate_int = int(raw_br)
            except Exception:
                bitrate_int = 256

            audio_args = final_audio_codec_args(codec, bitrate_int)
            sub_codec = str(item_settings.get("sub_codec", "srt")).lower()

            tr_to = str(item_settings.get("translate_to", "fr")).strip().lower()[:2] or "fr"
            tr_from_raw = str(item_settings.get("translate_from", "auto")).strip().lower()
            tr_from = None if tr_from_raw in ("auto", "none", "") else tr_from_raw[:2]

            opts = DubOptions(
                audio_ffmpeg_index=aud_idx,
                sub_choice=sub_choice,
                orig_audio_lang=str(item_settings.get("orig_audio_lang", "Original")).strip() or "Original",
                db_reduct=float(item_settings.get("ducking_db", -5.0)),
                offset_ms=int(item_settings.get("offset_ms", 0)),
                bg_mix=float(item_settings.get("bg_mix", 1.0)),
                tts_mix=float(item_settings.get("tts_mix", 1.0)),
                min_rate_tts=float(item_settings.get("min_rate_tts", 1.2)),
                max_rate_tts=float(item_settings.get("max_rate_tts", 1.8)),
                audio_codec=codec,
                audio_bitrate=bitrate_int,
                tts_engine=engine,
                voice_id=voice_id,
                audio_codec_args=audio_args,
                sub_codec=sub_codec,
                offset_video_ms=int(item_settings.get("offset_video_ms", 0)),
                ask_test_before_cleanup=False,
                translate=bool(item_settings.get("translate", False)),
                translate_to=tr_to,
                translate_from=tr_from,
                batch_mode=True,
                overwrite=overwrite_this,
                skip_existing=False,
                reuse_translated_subs=bool(item_settings.get("reuse_translated_subs", True)),
                ask_reuse_subs=False,
            )

            ui_adapter = QtUIAdapter(self, current_idx)
            svcs = Services(
                resolve_srt_for_video=resolve_srt_for_video,
                generate_dub_audio=generate_dub_audio,
                choose_files=lambda files: files,
                choose_audio_track=lambda vp: aud_idx if aud_idx is not None else 1,
                choose_subtitle_source=lambda vp: sub_choice if sub_choice is not None else ("srt", 0),
                ui=ui_adapter,
            )

            try:
                final_file = process_one_video(
                    input_video_path=video_path,
                    input_video_name=file_name,
                    output_dir_path=out_dir,
                    opts=opts,
                    svcs=svcs,
                )

                if self.is_paused or self.should_stop:
                    self._cleanup_tmp_files()
                    break

                if final_file and os.path.exists(final_file):
                    self.file_finished.emit(current_idx, video_path, final_file)
                else:
                    self.file_error.emit(current_idx, "Aucun fichier généré")
            except Exception as e:
                if self.is_paused or self.should_stop:
                    self._cleanup_tmp_files()
                    break
                self.file_error.emit(current_idx, str(e))

            current_idx += 1
            completed_global_pct = int(current_idx * 100 / max(1, total_files))
            self.global_progress.emit(completed_global_pct, f"Terminé {current_idx} / {total_files}")

        if not self.is_paused:
            self.global_progress.emit(100, "Tous les traitements sont terminés.")
            self.all_finished.emit()

    def _cleanup_tmp_files(self):
        try:
            tmp_d = io_fs.TMP_DIR
            if os.path.exists(tmp_d):
                for f in os.listdir(tmp_d):
                    p = os.path.join(tmp_d, f)
                    if os.path.isfile(p):
                        os.remove(p)
        except Exception:
            pass


class MainWindow(QMainWindow):
    """
    Fenêtre principale sobre et ergonomique inspirée de VidCoder.
    - Haut : 
      - Ligne 1 : Bouton 'Importer ▼' avec menu fichier/dossier, et bouton 'Paramètres' à droite.
      - Ligne 2 : Bouton 'Démarrer' (avec logo Play/Pause, grisé si file vide) et 'Vider la file'.
    - Centre : File d'attente avec barre de progression par fichier.
    - Bas : Progression globale et statut.
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AdDub — Doublage Automatique Audio & Vidéo")
        self.resize(900, 580)
        self.setAcceptDrops(False)

        self.default_settings: Dict[str, Any] = {}
        self.queue_items: List[Dict[str, Any]] = []
        self.completed_items: List[Dict[str, Any]] = []
        self.worker_thread: Optional[PipelineWorkerThread] = None

        self.is_running = False
        self.is_paused = False

        self._load_initial_defaults()
        self._init_ui()
        self._apply_vidcoder_theme()
        self._update_button_states()

    def _load_initial_defaults(self):
        f = effective_values()
        self.default_settings = {
            "output_dir": io_fs.join_output(""),
            "tts_engine": normalize_engine(f.get("tts_engine", "onecore")),
            "voice_id": f.get("voice_id", ""),
            "voice_lang": "fr-FR",
            "voice_display_name": "Voix par défaut",
            "min_rate_tts": float(f.get("min_rate_tts", 1.2)),
            "max_rate_tts": float(f.get("max_rate_tts", 1.8)),
            "ducking_db": float(f.get("ducking_db", f.get("db", -5.0))),
            "bg_mix": float(f.get("bg_mix", f.get("bg", 1.0))),
            "tts_mix": float(f.get("tts_mix", f.get("tts", 1.0))),
            "offset_ms": int(f.get("offset_ms", f.get("offset", 0))),
            "offset_video_ms": int(f.get("offset_video_ms", f.get("offset_video", 0))),
            "audio_codec": str(f.get("audio_codec", "ac3")).lower(),
            "audio_bitrate": str(f.get("audio_bitrate", "256")).replace("k", ""),
            "orig_audio_lang": str(f.get("orig_audio_lang", "Original")),
            "sub_codec": "srt",
            "translate": False,
            "translate_to": "fr",
            "translate_from": "auto",
            "reuse_translated_subs": True,
            "preserve_tree": False,
        }

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # -------------------------------------------------------------
        # 1. BANDEAU SUPÉRIEUR (Disposition propre à deux niveaux)
        # -------------------------------------------------------------
        header_frame = QFrame()
        header_frame.setObjectName("header_frame")
        header_layout = QVBoxLayout(header_frame)
        header_layout.setContentsMargins(10, 8, 10, 8)
        header_layout.setSpacing(8)

        # Ligne supérieure : Bouton Importer à gauche, Paramètres à droite
        top_row = QHBoxLayout()
        top_row.setSpacing(10)

        self.btn_import = QPushButton("📂 Importer Source ▼")
        self.btn_import.setObjectName("btn_import")
        self.btn_import.setFixedHeight(34)
        self.btn_import.setMinimumWidth(180)

        import_menu = QMenu(self)
        act_files = import_menu.addAction("Ouvrir un ou plusieurs fichiers vidéo...")
        act_files.triggered.connect(self._on_import_files)
        act_folder = import_menu.addAction("Ouvrir un dossier complet de vidéos...")
        act_folder.triggered.connect(self._on_import_folder)
        self.btn_import.setMenu(import_menu)
        top_row.addWidget(self.btn_import)

        top_row.addStretch()

        self.btn_settings = QPushButton("⚙ Paramètres")
        self.btn_settings.setObjectName("btn_settings")
        self.btn_settings.setFixedHeight(34)
        self.btn_settings.clicked.connect(self._open_default_settings)
        top_row.addWidget(self.btn_settings)

        header_layout.addLayout(top_row)

        # Ligne inférieure : Bouton Démarrer (avec logo Play) et Vider la file
        action_row = QHBoxLayout()
        action_row.setSpacing(10)

        self.btn_run = QPushButton("▶ Démarrer le traitement")
        self.btn_run.setObjectName("btn_run")
        self.btn_run.setFixedHeight(36)
        self.btn_run.setMinimumWidth(190)
        self.btn_run.clicked.connect(self._on_click_run_pause_resume)
        action_row.addWidget(self.btn_run)

        self.btn_clear = QPushButton("🗑 Vider la file")
        self.btn_clear.setObjectName("btn_clear")
        self.btn_clear.setFixedHeight(36)
        self.btn_clear.clicked.connect(self._clear_queue)
        action_row.addWidget(self.btn_clear)

        action_row.addStretch()
        header_layout.addLayout(action_row)

        main_layout.addWidget(header_frame)

        # -------------------------------------------------------------
        # 2. ZONE CENTRALE : ONGLETS (FILE D'ATTENTE & TERMINÉ)
        # -------------------------------------------------------------
        self.tabs_bottom = QTabWidget()

        # Onglet 1 : File d'attente
        tab_queue = QWidget()
        layout_queue = QVBoxLayout(tab_queue)
        layout_queue.setContentsMargins(4, 4, 4, 4)

        self.table_queue = QTableWidget(0, 6)
        self.table_queue.setHorizontalHeaderLabels([
            "Fichier vidéo",
            "Taille",
            "Piste audio",
            "Sous-titre",
            "Voix",
            "Progression"
        ])
        self.table_queue.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table_queue.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table_queue.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table_queue.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table_queue.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table_queue.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.table_queue.horizontalHeader().resizeSection(5, 180)

        self.table_queue.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_queue.setAlternatingRowColors(True)
        self.table_queue.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_queue.customContextMenuRequested.connect(self._on_queue_context_menu)
        layout_queue.addWidget(self.table_queue)
        self.tabs_bottom.addTab(tab_queue, "File d'attente (0)")

        # Onglet 2 : Terminé
        tab_done = QWidget()
        layout_done = QVBoxLayout(tab_done)
        layout_done.setContentsMargins(4, 4, 4, 4)

        self.table_done = QTableWidget(0, 3)
        self.table_done.setHorizontalHeaderLabels([
            "Fichier source",
            "Vidéo générée",
            "Statut"
        ])
        self.table_done.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table_done.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table_done.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table_done.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_done.setAlternatingRowColors(True)
        layout_done.addWidget(self.table_done)
        self.tabs_bottom.addTab(tab_done, "Terminé (0)")

        main_layout.addWidget(self.tabs_bottom, stretch=1)

        # -------------------------------------------------------------
        # 3. BAS DE FENÊTRE : PROGRESSION GLOBALE ET STATUT
        # -------------------------------------------------------------
        bottom_frame = QFrame()
        bottom_frame.setObjectName("bottom_frame")
        bottom_layout = QVBoxLayout(bottom_frame)
        bottom_layout.setContentsMargins(8, 6, 8, 6)
        bottom_layout.setSpacing(4)

        header_glob = QHBoxLayout()
        self.lbl_global_count = QLabel("Progression globale : [ 0 / 0 vidéo ]")
        self.lbl_global_count.setStyleSheet("font-weight: 600;")
        header_glob.addWidget(self.lbl_global_count)
        header_glob.addStretch()

        self.lbl_global_pct = QLabel("0 %")
        self.lbl_global_pct.setStyleSheet("font-weight: 600;")
        header_glob.addWidget(self.lbl_global_pct)
        bottom_layout.addLayout(header_glob)

        self.progress_global = QProgressBar()
        self.progress_global.setRange(0, 100)
        self.progress_global.setValue(0)
        self.progress_global.setFixedHeight(16)
        self.progress_global.setTextVisible(True)
        self.progress_global.setFormat("%p %")
        bottom_layout.addWidget(self.progress_global)

        self.lbl_status = QLabel("Prêt.")
        self.lbl_status.setStyleSheet("color: #AAAAAA;")
        bottom_layout.addWidget(self.lbl_status)

        main_layout.addWidget(bottom_frame)

    def _apply_vidcoder_theme(self):
        self.setStyleSheet("""
            QWidget {
                background-color: #1A1A1A;
                color: #E0E0E0;
                font-family: 'Segoe UI', system-ui, sans-serif;
                font-size: 12px;
            }
            #header_frame, #bottom_frame {
                background-color: #222222;
                border: 1px solid #333333;
                border-radius: 4px;
            }
            QPushButton {
                background-color: #2D2D2D;
                color: #E0E0E0;
                border: 1px solid #404040;
                border-radius: 4px;
                padding: 4px 12px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #383838;
                border-color: #555555;
            }
            QPushButton:pressed {
                background-color: #444444;
            }
            QPushButton:disabled {
                background-color: #1E1E1E;
                color: #555555;
                border-color: #2A2A2A;
            }
            QTableWidget {
                background-color: #1E1E1E;
                alternate-background-color: #242424;
                border: 1px solid #333333;
                border-radius: 4px;
                gridline-color: #2A2A2A;
                color: #E0E0E0;
            }
            QHeaderView::section {
                background-color: #252525;
                color: #D0D0D0;
                font-weight: 600;
                padding: 4px 8px;
                border: 1px solid #333333;
            }
            QProgressBar {
                background-color: #2A2A2A;
                border: 1px solid #444444;
                border-radius: 3px;
                text-align: center;
                color: #FFFFFF;
                font-weight: 600;
                font-size: 11px;
            }
            QProgressBar::chunk {
                background-color: #00C853;
                border-radius: 2px;
            }
            QTabWidget::pane {
                border: 1px solid #333333;
                background-color: #1E1E1E;
            }
            QTabBar::tab {
                background-color: #252525;
                color: #999999;
                padding: 6px 14px;
                border: 1px solid #333333;
                border-bottom: none;
                border-top-left-radius: 3px;
                border-top-right-radius: 3px;
                font-weight: 500;
            }
            QTabBar::tab:selected {
                background-color: #1E1E1E;
                color: #FFFFFF;
                border-bottom: 2px solid #00C853;
            }
            QMenu {
                background-color: #252525;
                color: #E0E0E0;
                border: 1px solid #444444;
            }
            QMenu::item:selected {
                background-color: #383838;
            }
        """)

    def _update_button_states(self):
        has_items = len(self.queue_items) > 0
        if not self.is_running:
            self.btn_run.setEnabled(has_items)
            self.btn_clear.setEnabled(has_items)
            self.btn_run.setText("▶ Démarrer le traitement")
        else:
            self.btn_clear.setEnabled(False)
            self.btn_run.setEnabled(True)

    # -------------------------------------------------------------
    # IMPORTATION & OUVERTURE DU PRÉPARATEUR DE LOT
    # -------------------------------------------------------------
    def _on_import_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Sélectionner des fichiers vidéo",
            "",
            "Vidéos (*.mkv *.mp4 *.avi *.mov *.ts *.m4v *.webm);;Tous les fichiers (*.*)"
        )
        if files:
            self._open_batch_importer(files)

    def _on_import_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Sélectionner un dossier de vidéos")
        if folder:
            files_found = []
            for root, _, files in os.walk(folder):
                for file in sorted(files):
                    ext = os.path.splitext(file)[1].lower()
                    if ext in VIDEO_EXTENSIONS:
                        files_found.append(os.path.join(root, file))
            if files_found:
                self._open_batch_importer(files_found)
            else:
                QMessageBox.information(self, "Aucune vidéo", "Aucun fichier vidéo trouvé dans ce dossier.")

    def _open_batch_importer(self, file_paths: List[str]):
        dlg = BatchImportDialog(file_paths, self.default_settings, self)
        if dlg.exec():
            for item in dlg.configured_items:
                self._add_to_queue(item)

    def _add_to_queue(self, item: Dict[str, Any]):
        video_path = item["path"]
        st = item.get("settings", {})

        row = self.table_queue.rowCount()
        self.table_queue.insertRow(row)

        file_name = os.path.basename(video_path)
        sz_str = "Inconnu"
        try:
            sz_str = f"{os.path.getsize(video_path) / (1024*1024):.1f} Mo"
        except Exception:
            pass

        item_name = QTableWidgetItem(file_name)
        item_name.setToolTip(video_path)
        self.table_queue.setItem(row, 0, item_name)
        self.table_queue.setItem(row, 1, QTableWidgetItem(sz_str))
        self.table_queue.setItem(row, 2, QTableWidgetItem(str(st.get("audio_label", "Auto"))[:30]))
        self.table_queue.setItem(row, 3, QTableWidgetItem(str(st.get("sub_label", "Auto"))[:30]))
        self.table_queue.setItem(row, 4, QTableWidgetItem(str(st.get("voice_display_name", "Défaut"))))

        pbar = QProgressBar()
        pbar.setRange(0, 100)
        pbar.setValue(0)
        pbar.setFixedHeight(16)
        pbar.setTextVisible(True)
        pbar.setFormat("En attente")
        self.table_queue.setCellWidget(row, 5, pbar)

        self.queue_items.append(item)
        self._update_counts()
        self._update_button_states()

    def _clear_queue(self):
        if self.is_running:
            QMessageBox.warning(self, "Action impossible", "Un traitement est en cours. Veuillez d'abord le mettre en pause.")
            return
        self.queue_items.clear()
        self.table_queue.setRowCount(0)
        self._update_counts()
        self._update_button_states()

    def _on_queue_context_menu(self, pos: QPoint):
        row = self.table_queue.rowAt(pos.y())
        if row < 0 or row >= len(self.queue_items):
            return

        menu = QMenu(self)
        act_remove = menu.addAction("Supprimer de la file d'attente")
        act_open_dir = menu.addAction("Ouvrir le dossier contenant la vidéo...")

        action = menu.exec(self.table_queue.viewport().mapToGlobal(pos))
        if action == act_remove:
            if self.is_running:
                QMessageBox.warning(self, "Action impossible", "Traitement en cours.")
                return
            self.table_queue.removeRow(row)
            self.queue_items.pop(row)
            self._update_counts()
            self._update_button_states()
        elif action == act_open_dir:
            import subprocess
            folder = os.path.dirname(self.queue_items[row]["path"])
            subprocess.Popen(f'explorer "{folder}"')

    def _update_counts(self):
        q_count = len(self.queue_items)
        d_count = len(self.completed_items)
        self.tabs_bottom.setTabText(0, f"File d'attente ({q_count})")
        self.tabs_bottom.setTabText(1, f"Terminé ({d_count})")
        self.lbl_global_count.setText(f"Progression globale : [ {d_count} / {q_count + d_count} vidéo{'s' if (q_count+d_count) > 1 else ''} ]")

    def _open_default_settings(self):
        dlg = DefaultSettingsDialog(self.default_settings, self)
        if dlg.exec():
            self.default_settings.update(dlg.settings)

    # -------------------------------------------------------------
    # GESTION DÉMARRER / PAUSE / REPRENDRE
    # -------------------------------------------------------------
    def _on_click_run_pause_resume(self):
        if not self.is_running:
            if not self.queue_items:
                return
            self._start_processing()
        else:
            if not self.is_paused:
                self._pause_processing()
            else:
                self._resume_processing()

    def _start_processing(self):
        self.is_running = True
        self.is_paused = False
        self.btn_run.setText("⏸ Mettre en pause")
        self.btn_clear.setEnabled(False)

        self.worker_thread = PipelineWorkerThread(self.queue_items, self.default_settings)
        self.worker_thread.file_started.connect(self._on_worker_file_started)
        self.worker_thread.step_progress.connect(self._on_worker_step_progress)
        self.worker_thread.pct_progress.connect(self._on_worker_pct_progress)
        self.worker_thread.file_finished.connect(self._on_worker_file_finished)
        self.worker_thread.file_skipped.connect(self._on_worker_file_skipped)
        self.worker_thread.file_error.connect(self._on_worker_file_error)
        self.worker_thread.global_progress.connect(self._on_worker_global_progress)
        self.worker_thread.ask_conflict.connect(self._on_worker_ask_conflict)
        self.worker_thread.all_finished.connect(self._on_worker_all_finished)
        self.worker_thread.start()

    def _pause_processing(self):
        self.is_paused = True
        self.btn_run.setText("▶ Reprendre le traitement")
        self.lbl_status.setText("Pause demandée : nettoyage en cours...")
        if self.worker_thread:
            self.worker_thread.stop_or_pause()

    def _resume_processing(self):
        self.is_paused = False
        self.btn_run.setText("⏸ Mettre en pause")
        self.lbl_status.setText("Reprise du traitement...")
        self._start_processing()

    # -------------------------------------------------------------
    # SIGNAUX DU WORKER THREAD
    # -------------------------------------------------------------
    def _on_worker_file_started(self, idx: int, filename: str, item_data: dict):
        if idx < self.table_queue.rowCount():
            pbar = self.table_queue.cellWidget(idx, 5)
            if isinstance(pbar, QProgressBar):
                pbar.setValue(0)
                pbar.setFormat("%p %")

    def _on_worker_step_progress(self, idx: int, msg: str):
        self.lbl_status.setText(msg)

    def _on_worker_pct_progress(self, idx: int, pct: int):
        if idx < self.table_queue.rowCount():
            pbar = self.table_queue.cellWidget(idx, 5)
            if isinstance(pbar, QProgressBar):
                pbar.setValue(pct)
                pbar.setFormat(f"{pct} %")

    def _on_worker_file_finished(self, idx: int, src_path: str, out_path: str):
        if idx < len(self.queue_items):
            done_item = self.queue_items.pop(idx)
            self.table_queue.removeRow(idx)

            row = self.table_done.rowCount()
            self.table_done.insertRow(row)
            self.table_done.setItem(row, 0, QTableWidgetItem(os.path.basename(src_path)))
            out_item = QTableWidgetItem(out_path)
            out_item.setToolTip(out_path)
            self.table_done.setItem(row, 1, out_item)
            item_stat = QTableWidgetItem("Succès")
            item_stat.setForeground(QColor("#00C853"))
            self.table_done.setItem(row, 2, item_stat)

            self.completed_items.append(done_item)
            self._update_counts()
            self._update_button_states()

    def _on_worker_file_skipped(self, idx: int, src_path: str, reason: str):
        if idx < len(self.queue_items):
            done_item = self.queue_items.pop(idx)
            self.table_queue.removeRow(idx)

            row = self.table_done.rowCount()
            self.table_done.insertRow(row)
            self.table_done.setItem(row, 0, QTableWidgetItem(os.path.basename(src_path)))
            self.table_done.setItem(row, 1, QTableWidgetItem(reason))
            item_stat = QTableWidgetItem("Sauté")
            item_stat.setForeground(QColor("#FFAA00"))
            self.table_done.setItem(row, 2, item_stat)

            self.completed_items.append(done_item)
            self._update_counts()
            self._update_button_states()

    def _on_worker_file_error(self, idx: int, err_msg: str):
        self.lbl_status.setText(f"Erreur : {err_msg}")
        if idx < self.table_queue.rowCount():
            pbar = self.table_queue.cellWidget(idx, 5)
            if isinstance(pbar, QProgressBar):
                pbar.setFormat("Échec")

    def _on_worker_global_progress(self, pct: int, status_desc: str):
        self.progress_global.setValue(pct)
        self.lbl_global_pct.setText(f"{pct} %")
        self.lbl_status.setText(status_desc)

    def _on_worker_ask_conflict(self, filename: str, out_path: str):
        dlg = ConflictDialog(filename, out_path, self)
        dlg.exec()
        if self.worker_thread:
            self.worker_thread.set_conflict_response(dlg.choice_result)

    def _on_worker_all_finished(self):
        self.is_running = False
        self.is_paused = False
        self.lbl_status.setText("Tous les traitements sont terminés.")
        self._update_button_states()


def main():
    init_language()
    io_fs.ensure_base_dirs()

    app = QApplication(sys.argv)
    app.setApplicationName("AdDub")
    app.setStyle("Fusion")

    win = MainWindow()
    win.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
