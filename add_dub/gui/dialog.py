"""Configuration d'un lot : détection, sélection et exceptions par vidéo."""
from copy import deepcopy
import os
from pathlib import Path
from functools import lru_cache

from PySide6.QtCore import Qt, QTimer, QFileInfo, QSignalBlocker
from PySide6.QtGui import QColor, QPixmap, QIcon, QBrush
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QSplitter, QWidget, QLabel, QTreeWidget,
    QTreeWidgetItem, QPushButton, QCheckBox, QRadioButton, QButtonGroup,
    QLineEdit, QFileDialog, QMessageBox, QGroupBox, QStyle, QFileIconProvider, QProgressBar, QStyleFactory,
    QPlainTextEdit, QApplication, QMenu, QScrollArea, QHeaderView, QGraphicsOpacityEffect,
)
from add_dub.gui.model import discover, inspect_video, adapt_settings
from add_dub.gui.widgets import SettingsEditor, SmoothTreeWidget, ConfigButton
from add_dub.gui.theme import icons8_icon
from add_dub.gui.batch import export_commands, batch_text, open_batch_terminal

ROLE = Qt.ItemDataRole.UserRole
COMMON = '__common__'


@lru_cache(maxsize=2)
def yellow_folder_icon(opened):
    """Icône SVG Icons8 en couleur, nette à toutes les tailles."""
    icon = icons8_icon('folder-open' if opened else 'folder')
    if not icon.isNull():
        return icon
    # Repli natif si une distribution ne contient pas les ressources.
    style = QStyleFactory.create('Fusion')
    kind = QStyle.StandardPixmap.SP_DirOpenIcon if opened else QStyle.StandardPixmap.SP_DirClosedIcon
    source = style.standardIcon(kind)
    icon = QIcon()
    for size in (16, 24, 32, 48, 64):
        image = source.pixmap(size, size).toImage()
        for y in range(image.height()):
            for x in range(image.width()):
                color = image.pixelColor(x, y)
                hue, saturation, lightness, alpha = color.getHslF()
                if color.alpha() and 0.48 <= hue <= 0.72:
                    image.setPixelColor(x, y, QColor.fromHslF(0.12, saturation, lightness, alpha))
        icon.addPixmap(QPixmap.fromImage(image))
    return icon


class ConfigureDialog(QDialog):
    def __init__(self, job, tasks, parent=None):
        super().__init__(parent)
        from add_dub.cli.args import parse_args
        from add_dub.gui.model import Settings
        self.config_defaults = Settings.from_args(parse_args([])[0])
        self.job = deepcopy(job)
        self.job.recursive = True
        self.job.preserve_tree = True
        self.tasks = tasks
        self._closed = False
        self.generation = 0
        self.detect_generation = 0
        self.current_path = COMMON
        self.reference = None
        self.loaded = False
        self.initialized = bool(job.videos)
        self.known = {v.path: v for v in self.job.videos}
        self.file_items = {}
        self.icon_provider = QFileIconProvider()
        self.setWindowTitle('Configurer le doublage - add_dub')
        # La configuration est une vraie fenêtre de travail : elle reste
        # redimensionnable et s’ouvre agrandie comme la fenêtre principale.
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        available = self.screen().availableGeometry()
        self.resize(min(1220, available.width() - 40), min(850, available.height() - 80))
        self.setMinimumSize(860, 560)
        self._maximize_pending = True
        self.finished.connect(self.closed)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(22, 20, 22, 20)
        outer.setSpacing(14)
        self.summary = QLabel('Recherche des vidéos…')
        self.summary.setWordWrap(True)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.columns = splitter
        outer.addWidget(splitter, 1)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 8, 0)
        left_layout.setSpacing(12)
        header_height = max(48, self.fontMetrics().lineSpacing() * 2 + 12)
        left_header = QWidget()
        left_header.setFixedHeight(header_height)
        header_layout = QVBoxLayout(left_header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(0)
        left_layout.addWidget(left_header)
        self.has_folders = any(os.path.isdir(p) for p in self.job.sources)
        self.scan_progress = QProgressBar()
        self.scan_progress.setObjectName('scanProgress')
        self.scan_progress.setAccessibleName('Progression de l’analyse des vidéos')
        self.scan_progress.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scan_progress.setFormat('%v/%m')
        header_layout.addWidget(self.scan_progress, alignment=Qt.AlignmentFlag.AlignVCenter)
        self.summary.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header_layout.addWidget(self.summary)
        self.summary.hide()
        self.tree = SmoothTreeWidget()
        self.tree.setHeaderLabels(['Fichiers', 'État', 'Configuration'])
        self.tree.setTreePosition(0)
        self.tree.header().moveSection(2, 0)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.setColumnWidth(2, 54)
        self.tree.setHeaderHidden(True)
        self.tree.setColumnHidden(1, True)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.folder_menu)
        self.tree.setAccessibleName('Sélection des vidéos et des dossiers')
        self.tree.setObjectName('configurationFiles')
        self.tree.setColumnWidth(0, 220)
        self.tree.setIconSize(QPixmap(28, 28).size())
        self.tree.setMinimumWidth(270)
        left_layout.addWidget(self.tree, 1)
        left_hint = QLabel('Cochez les vidéos à traiter. Un dossier partiellement sélectionné porte une coche intermédiaire. Les vidéos sans sous-titres sont désactivées.')
        left_hint.setWordWrap(True)
        self.tree.setToolTip(left_hint.text())
        left_hint.deleteLater()
        splitter.addWidget(left)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 0, 0, 0)
        right_layout.setSpacing(12)
        right_header = QWidget()
        right_header.setFixedHeight(header_height)
        reference_layout = QVBoxLayout(right_header)
        reference_layout.setContentsMargins(0, 0, 0, 0)
        reference_layout.setSpacing(0)
        right_layout.addWidget(right_header)
        self.scope = QLabel(self)
        self.scope.setObjectName('scope')
        self.scope.setWordWrap(False)
        self.scope.show()
        self.config_bar = QHBoxLayout()
        self.config_bar.setContentsMargins(0, 0, 0, 0)
        self.config_bar.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.config_bar.setSpacing(10)
        nav = QWidget()
        nav.setLayout(self.config_bar)
        nav_scroll = QScrollArea()
        nav_scroll.setWidgetResizable(True)
        nav_scroll.setContentsMargins(0, 0, 0, 0)
        nav_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        nav_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        nav_scroll.setWidget(nav)
        nav_scroll.setFixedHeight(46)
        right_layout.addWidget(nav_scroll)
        reference_layout.addWidget(self.scope)
        self.rebuild_config_buttons()
        self.reference_label = QLabel()
        self.reference_label.setWordWrap(False)
        self.reference_label.setMinimumWidth(0)
        self.reference_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        reference_layout.addWidget(self.reference_label, 1)
        self.reset = QPushButton('Revenir aux réglages communs')
        self.reset.hide()
        self.reset.setAccessibleName('Supprimer les réglages personnalisés de cette vidéo')
        self.reset.clicked.connect(self.reset_file)
        reference_layout.addWidget(self.reset, alignment=Qt.AlignmentFlag.AlignVCenter)
        self.editor = SettingsEditor(tasks)
        from add_dub.gui.preview import PreviewPane
        self.preview = PreviewPane(self, tasks)
        self.editor.addTab(self.preview, 'Essai')
        self.editor.currentChanged.connect(self.refresh_preview)
        self.editor.setEnabled(False)
        right_layout.addWidget(self.editor, 1)
        splitter.addWidget(right)
        splitter.setSizes([380, 800])
        bottom_options = QHBoxLayout()
        bottom_options.setSpacing(splitter.handleWidth() + 16)
        output_panel = QWidget()
        output_panel.setObjectName('outputPanel')
        output_layout = QVBoxLayout(output_panel)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.setSpacing(14)
        output_row = QHBoxLayout()
        output_row.setContentsMargins(0, 0, 0, 0)
        output_row.setSpacing(12)
        output_icon = QLabel()
        output_icon.setPixmap(yellow_folder_icon(False).pixmap(22, 22))
        output_row.addWidget(output_icon)
        output_title = QLabel('Sorti')
        output_row.addWidget(output_title)
        self.output = QLineEdit(self.job.output)
        self.output.setAccessibleName('Dossier de sortie du lot')
        output_row.addWidget(self.output, 1)
        browse = QPushButton('Parcourir…')
        browse.clicked.connect(self.choose_output)
        output_row.addWidget(browse)
        output_layout.addLayout(output_row)
        bottom_options.addWidget(output_panel, 1)
        # Pour un seul fichier, conserver la colonne gauche vide afin que le
        # dossier de sortie reste aligné sur la colonne droite, comme pour un
        # lot de plusieurs vidéos.
        self.bottom_placeholder = QWidget()
        self.bottom_placeholder.setVisible(False)
        bottom_options.insertWidget(0, self.bottom_placeholder, 1)
        self.batch_options = QWidget()
        options = QVBoxLayout(self.batch_options)
        options.setContentsMargins(0, 0, 0, 0)
        options.setSpacing(8)
        policy_row = QVBoxLayout()
        self.resume = QRadioButton('Reprendre : ignorer les sorties existantes')
        self.overwrite = QRadioButton('Remplacer les sorties existantes')
        self.policy = QButtonGroup(self)
        self.policy.addButton(self.resume)
        self.policy.addButton(self.overwrite)
        self.resume.setChecked(self.job.resume)
        self.overwrite.setChecked(not self.job.resume)
        policy_row.addWidget(self.resume)
        policy_row.addWidget(self.overwrite)
        options.addStretch(1)
        options.addLayout(policy_row)
        options.addStretch(1)
        # Les options et le dossier de sortie partagent la même ligne basse,
        # toujours visible sous la zone centrale redimensionnable.
        bottom_options.insertWidget(0, self.batch_options, 1)
        outer.addLayout(bottom_options)
        splitter.splitterMoved.connect(self.align_bottom_columns)
        QTimer.singleShot(0, self.align_bottom_columns)
        footer_panel = QWidget()
        footer = QHBoxLayout(footer_panel)
        footer.setContentsMargins(0, 0, 0, 0)
        footer.setSpacing(12)
        footer.addStretch()
        self.batch_open = QPushButton('Commandes Batch…')
        self.batch_open.clicked.connect(self.show_batch)
        footer.addWidget(self.batch_open)
        cancel = QPushButton('Annuler')
        cancel.clicked.connect(self.reject)
        footer.addWidget(cancel)
        self.add = QPushButton('Enregistrer les modifications' if job.videos else 'Ajouter à la liste d’attente')
        self.add.setObjectName('primary')
        self.add.setMinimumHeight(46)
        self.add.setEnabled(False)
        self.add.clicked.connect(self.validate)
        footer.addWidget(self.add)
        output_layout.addWidget(footer_panel)
        self.tree.model().dataChanged.connect(self.tree_data_changed)
        self.tree.currentItemChanged.connect(self.select_item)
        self.tree.itemExpanded.connect(lambda item: self.set_folder_icon(item, True))
        self.tree.itemCollapsed.connect(lambda item: self.set_folder_icon(item, False))
        self.editor.changed.connect(self.edited)
        self.batch_page = QDialog(self)
        self.batch_page.setWindowTitle('Commandes Batch du lot')
        self.batch_page.setModal(True)
        self.batch_page.resize(min(1050, available.width() - 60), min(620, available.height() - 80))
        batch_layout = QVBoxLayout(self.batch_page)
        batch_layout.setContentsMargins(20, 20, 20, 20)
        batch_layout.setSpacing(16)
        self.batch_summary = QLabel()
        self.batch_summary.setWordWrap(True)
        batch_layout.addWidget(self.batch_summary)
        explanation = QLabel('Commandes pour toutes les vidéos cochées, avec leurs réglages et dossiers de sortie. '
                             'L’exécution dans CMD traite le lot à la suite, hors de la file d’attente.')
        explanation.setWordWrap(True)
        batch_layout.addWidget(explanation)
        self.batch_text = QPlainTextEdit()
        self.batch_text.setReadOnly(True)
        self.batch_text.setAccessibleName('Commande batch')
        batch_layout.addWidget(self.batch_text, 1)
        batch_buttons = QHBoxLayout()
        self.batch_copy = QPushButton('Copier les commandes')
        self.batch_execute = QPushButton('Exécuter dans CMD')
        batch_buttons.addWidget(self.batch_copy)
        batch_buttons.addWidget(self.batch_execute)
        batch_buttons.addStretch()
        close_batch = QPushButton('Fermer')
        close_batch.clicked.connect(self.batch_page.reject)
        batch_buttons.addWidget(close_batch)
        for button in (self.batch_copy, self.batch_execute, close_batch):
            button.setAutoDefault(False)
        batch_layout.addLayout(batch_buttons)
        self.batch_command = None
        self.batch_copy.clicked.connect(self.copy_batch)
        self.batch_execute.clicked.connect(self.execute_batch)
        self.editor.changed.connect(self.refresh_batch)
        self.output.textChanged.connect(self.refresh_batch)
        self.resume.toggled.connect(self.refresh_batch)
        QTimer.singleShot(0, self.scan)

    def show_batch(self):
        self.batch_page.open()
        self.refresh_batch()

    def refresh_batch(self, *_):
        if not self.batch_page.isVisible():
            return
        self.batch_command = None
        self.batch_summary.setText('Analyse des fichiers en cours… Toutes les configurations seront prises en compte.')
        try:
            if not self.loaded or self.editor.video is None:
                raise ValueError('Attendez la détection des pistes.')
            self.save_current()
            self.sync_selection()
            self.batch_summary.setText(f'{len(self.job.selected)} vidéo(s) cochée(s), toutes configurations comprises.')
            job = deepcopy(self.job)
            job.output = self.output.text().strip()
            job.preserve_tree = True
            job.resume = self.resume.isChecked()
            job.dry_run = False
            commands = export_commands(job)
            self.batch_text.setPlainText(batch_text(commands))
            self.batch_command = commands
            self.batch_execute.setText(f'Exécuter {len(job.selected)} vidéo(s) dans CMD')
        except ValueError as exc:
            self.batch_text.setPlainText(str(exc))
        self.batch_copy.setEnabled(self.batch_command is not None)
        self.batch_execute.setEnabled(self.batch_command is not None)

    def copy_batch(self):
        self.refresh_batch()
        if self.batch_command:
            QApplication.clipboard().setText(self.batch_text.toPlainText())

    def execute_batch(self):
        self.refresh_batch()
        if self.batch_command:
            try:
                open_batch_terminal(self.batch_command)
            except (OSError, ValueError) as exc:
                QMessageBox.warning(self, 'Impossible d’ouvrir CMD', str(exc))

    def showEvent(self, event):
        super().showEvent(event)
        if self._maximize_pending:
            self._maximize_pending = False
            # L’état est appliqué après la création de la fenêtre native,
            # ce qui évite que QDialog.exec() ne le remplace par une taille
            # normale et ne laisse la fenêtre principale visible derrière.
            QTimer.singleShot(0, self.maximize_initial_window)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'batch_options'):
            QTimer.singleShot(0, self.align_bottom_columns)

    def align_bottom_columns(self, *_):
        if not self._closed:
            width = max(0, self.columns.sizes()[0] - 8)
            self.batch_options.setFixedWidth(width)
            self.bottom_placeholder.setFixedWidth(width)

    def maximize_initial_window(self):
        if not self._closed:
            self.showNormal()
            # Donner une géométrie cohérente avec l'écran à la fenêtre native
            # avant la maximisation (notamment avec un DPI Windows de 125 %).
            available = self.screen().availableGeometry()
            self.setGeometry(available.adjusted(0, 30, 0, -10))
            self.showMaximized()

    def closed(self):
        self.preview.shutdown()
        self._closed = True
        self.generation += 1
        self.detect_generation += 1

    def choose_output(self):
        path = QFileDialog.getExistingDirectory(self, 'Dossier de sortie', self.output.text())
        if path:
            self.output.setText(path)

    def save_current(self):
        if not self.loaded:
            return
        settings = self.editor.settings()
        if self.current_path == COMMON:
            self.job.common = settings
        elif self.current_path in self.job.folder_configs:
            self.job.folder_configs[self.current_path] = settings
        else:
            video = next((v for v in self.job.videos if v.path == self.current_path), None)
            if video:
                inherited = adapt_settings(self.job.common, video)
                if settings == inherited:
                    self.job.overrides.pop(video.path, None)
                else:
                    self.job.overrides[video.path] = settings

    def edited(self):
        if self.loaded:
            self.save_current()
            self.scope_text()
            self.update_summary()

    def scope_text(self):
        folder = self.current_path if self.current_path in self.job.folder_configs else None
        text = (f'Config. n°{self.job.config_numbers[folder]} - {folder} et ses sous-dossiers'
                if folder else 'Général - vidéos sans configuration de dossier')
        self.scope.setText(text)
        self.reset.hide()
        self.tree.active_config_scope = folder
        self.tree.viewport().update()
        for p, item in getattr(self, 'folder_items', {}).items():
            marker = self.tree.itemWidget(item, 2)
            if marker:
                effect = marker.graphicsEffect()
                if effect is None:
                    effect = QGraphicsOpacityEffect(marker)
                    marker.setGraphicsEffect(effect)
                effect.setOpacity(1.0 if p == folder else 0.57)
        for path, button in getattr(self, 'config_buttons', {}).items():
            button.setChecked(path == self.current_path)

    def rebuild_config_buttons(self):
        while self.config_bar.count():
            item = self.config_bar.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.config_buttons = {}
        for path in [COMMON, *self.job.folder_configs]:
            label = 'Général' if path == COMMON else f'Config. n°{self.job.config_numbers[path]}'
            button = ConfigButton(label)
            button.setObjectName('configSelector')
            button.setStyleSheet('min-height: 36px; max-height: 36px; padding: 0; border: none;')
            button.setFixedHeight(36)
            button.setMinimumWidth(130)
            button.setCheckable(True)
            button.setToolTip('Réglages généraux' if path == COMMON else path)
            button.clicked.connect(lambda checked=False, p=path: self.open_config(p))
            self.config_bar.addWidget(button, alignment=Qt.AlignmentFlag.AlignTop)
            self.config_buttons[path] = button
        self.config_bar.addStretch()

    def reference_for(self, folder):
        candidates = [v for v in self.job.videos if v.eligible and
                      (folder == COMMON or Path(folder) in Path(v.path).parents)]
        candidates.sort(key=lambda v: (len(Path(v.path).parts), v.path.casefold()))
        return candidates[0] if candidates else None

    def open_config(self, folder):
        self.save_current()
        self.detect_generation += 1
        video = self.reference_for(folder)
        if video:
            self.load_scope(folder, video)

    def create_folder_config(self, folder):
        self.save_current()
        if folder not in self.job.folder_configs:
            self.job.folder_configs[folder] = deepcopy(self.config_defaults)
            self.job.config_numbers[folder] = self.job.next_config_number
            self.job.next_config_number += 1
        self.rebuild_config_buttons()
        self.update_config_markers()
        self.open_config(folder)
        self.update_summary()

    def remove_folder_config(self, folder):
        self.save_current()
        self.job.folder_configs.pop(folder, None)
        self.job.config_numbers.pop(folder, None)
        self.loaded = False
        self.rebuild_config_buttons()
        self.update_config_markers()
        self.open_config(self.job.folder_scope(folder) or COMMON)
        self.update_summary()

    def folder_menu(self, position):
        item = self.tree.itemAt(position)
        folder = item.data(0, ROLE + 1) if item else None
        if not folder or not self.reference_for(folder):
            return
        menu = QMenu(self)
        if folder in self.job.folder_configs:
            menu.addAction('Modifier les réglages de ce dossier', lambda: self.open_config(folder))
            menu.addAction('Supprimer la configuration de ce dossier', lambda: self.remove_folder_config(folder))
        else:
            menu.addAction('Personnaliser les réglages de ce dossier', lambda: self.create_folder_config(folder))
        menu.exec(self.tree.viewport().mapToGlobal(position))

    def update_config_markers(self):
        for path, item in {**getattr(self, 'folder_items', {}), **self.file_items}.items():
            video = self.known.get(path)
            if video and not video.eligible:
                continue
            item.setData(0, ROLE + 8, self.job.folder_scope(path))
            for column in range(self.tree.columnCount()):
                item.setBackground(column, QBrush())
        for folder, item in getattr(self, 'folder_items', {}).items():
            number = self.job.config_numbers.get(folder)
            previous = self.tree.itemWidget(item, 2)
            if previous:
                self.tree.removeItemWidget(item, 2)
                previous.deleteLater()
            if number:
                button = QPushButton(f'⚙ {number}')
                button.setStyleSheet('padding: 0; border: none; min-height: 24px;')
                button.setToolTip(f'Ouvrir Config. n°{number} - {folder}')
                button.clicked.connect(lambda checked=False, p=folder: self.open_config(p))
                self.tree.setItemWidget(item, 2, button)
            item.setToolTip(0, folder + (f' - Config. n°{number}' if number else ''))

    def scan(self):
        self.save_current()
        self.generation += 1
        self.detect_generation += 1
        generation = self.generation
        self.loaded = False
        self.editor.setEnabled(False)
        self.add.setEnabled(False)
        self.tree.setEnabled(False)
        self.summary.setText('Détection des vidéos, des pistes audio et des sous-titres…')
        sources = list(self.job.sources)
        self.scan_progress.setRange(0, 0)
        self.scan_progress.show()
        self.summary.hide()
        known = deepcopy(self.known)
        def progress(counts):
            if generation != self.generation:
                return
            completed, total = counts
            self.scan_progress.setRange(0, max(1, total))
            self.scan_progress.setFormat('%v/%m' if total else '0/0')
            self.scan_progress.setValue(completed)

        def work(report):
            videos = discover(sources, True)
            report((0, len(videos)))
            result = []
            for video in videos:
                if video.path in known:
                    video.selected = known[video.path].selected
                result.append(inspect_video(video))
                report((len(result), len(videos)))
            return result
        def done(videos, error):
            if generation != self.generation:
                return
            self.tree.setEnabled(True)
            self.scan_progress.hide()
            self.summary.show()
            if error:
                self.scan_progress.hide()
                self.summary.setText(f'Détection impossible : {error}')
                return
            progress((len(videos), len(videos)))
            self.job.videos = videos
            self.known.update({v.path: v for v in videos})
            self.reference = next((v for v in videos if v.eligible), None)
            if self.reference and not self.initialized:
                self.job.common = adapt_settings(self.job.common, self.reference)
                self.initialized = True
            self.build_tree()
            # Les options de sortie restent toujours disponibles, y compris
            # lorsqu'un seul fichier est ajouté.
            self.batch_options.setVisible(True)
            self.bottom_placeholder.setVisible(False)
            self.add.setEnabled(bool(self.reference))
            self.update_summary()
            if self.reference:
                self.load_scope(COMMON, self.reference)
            else:
                self.scope.setText('Aucune vidéo admissible. Vérifiez les pistes audio et les sous-titres.')
                self.reset.hide()
        self.tasks.run(self, work, done, progress=progress)

    def build_tree(self):
        self.tree.blockSignals(True)
        self.tree.clear()
        self.file_items = {}
        folders = {}
        self.folder_items = folders
        for video in self.job.videos:
            parent = self.tree
            if video.root:
                relative = Path(os.path.relpath(os.path.dirname(video.path), video.root))
                directories = [Path(video.root)]
                for part in relative.parts:
                    if part != '.':
                        directories.append(directories[-1] / part)
                for directory in directories:
                    key = str(directory)
                    if key not in folders:
                        item = QTreeWidgetItem(parent, [directory.name or key, 'Dossier'])
                        item.setIcon(0, self.folder_icon(False))
                        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                        item.setCheckState(0, Qt.CheckState.Unchecked)
                        item.setToolTip(0, key)
                        item.setData(0, ROLE + 1, key)
                        folders[key] = item
                    parent = folders[key]
            item = QTreeWidgetItem(parent, [Path(video.path).name, 'Commun' if video.eligible else video.reason])
            item.setIcon(0, self.video_icon(video.path))
            item.setData(0, ROLE, video.path)
            item.setToolTip(0, video.path)
            item.setToolTip(1, video.reason)
            if video.eligible:
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(0, Qt.CheckState.Checked if video.selected else Qt.CheckState.Unchecked)
            else:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled & ~Qt.ItemFlag.ItemIsSelectable)
                for col in (0, 1):
                    item.setBackground(col, QColor('#601a22'))
                    item.setForeground(col, QColor('#ffffff'))
            self.file_items[video.path] = item
        self.update_config_markers()
        self.refresh_folders()
        self.tree.expandAll()
        # Les signaux sont bloqués pendant la construction : synchroniser aussi les icônes.
        for item in folders.values():
            self.set_folder_icon(item, item.isExpanded())
        self.tree.blockSignals(False)
        self.scope_text()

    def video_icon(self, path):
        """Utilise l’icône d’association Windows du fichier vidéo."""
        icon = self.icon_provider.icon(QFileInfo(path))
        return icon if not icon.isNull() else self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)

    def folder_icon(self, opened):
        """Icône jaune de dossier, fermée ou ouverte."""
        icon = yellow_folder_icon(opened)
        if not icon.isNull():
            return icon
        pixmap = (QStyle.StandardPixmap.SP_DirOpenIcon if opened
                  else QStyle.StandardPixmap.SP_DirClosedIcon)
        return self.style().standardIcon(pixmap)

    def set_folder_icon(self, item, opened):
        if item and item.childCount() and not item.data(0, ROLE):
            # Une modification d’icône émet aussi itemChanged : ce n’est pas un clic sur la case.
            with QSignalBlocker(self.tree):
                item.setIcon(0, self.folder_icon(opened))

    def descendants(self, item):
        for i in range(item.childCount()):
            child = item.child(i)
            if child.data(0, ROLE) in self.file_items:
                if child.flags() & Qt.ItemFlag.ItemIsEnabled:
                    yield child
            else:
                yield from self.descendants(child)

    def refresh_folders(self):
        def walk(item):
            for i in range(item.childCount()):
                walk(item.child(i))
            if item.childCount():
                children = list(self.descendants(item))
                states = [c.checkState(0) == Qt.CheckState.Checked for c in children]
                state = Qt.CheckState.Checked if states and all(states) else Qt.CheckState.PartiallyChecked if any(states) else Qt.CheckState.Unchecked
                item.setCheckState(0, state)
        for i in range(self.tree.topLevelItemCount()):
            walk(self.tree.topLevelItem(i))

    def check_item(self, item, column):
        if column != 0:
            return
        self.tree.blockSignals(True)
        if item.childCount():
            state = Qt.CheckState.Checked if item.checkState(0) != Qt.CheckState.Unchecked else Qt.CheckState.Unchecked
            for child in self.descendants(item):
                child.setCheckState(0, state)
        for video in self.job.videos:
            video.selected = video.eligible and self.file_items[video.path].checkState(0) == Qt.CheckState.Checked
        self.refresh_folders()
        self.tree.blockSignals(False)
        self.update_summary()

    def tree_data_changed(self, top_left, bottom_right, roles):
        if self.tree.signalsBlocked() or Qt.ItemDataRole.CheckStateRole not in roles:
            return
        self.check_item(self.tree.itemFromIndex(top_left), top_left.column())

    def sync_selection(self):
        """Les cases visibles font autorité, y compris après une détection asynchrone."""
        for video in self.job.videos:
            item = self.file_items.get(video.path)
            video.selected = bool(video.eligible and item and item.checkState(0) == Qt.CheckState.Checked)

    def update_summary(self):
        self.summary.setText(f'{len(self.job.selected)} vidéo(s) sélectionnée(s) sur {len(self.job.videos)} · {len(self.job.folder_configs)} configuration(s)')
        if hasattr(self, 'batch_page'):
            self.refresh_batch()

    def select_item(self, item, previous):
        if not item:
            return
        path = item.data(0, ROLE + 1) or item.data(0, ROLE)
        self.open_config(self.job.folder_scope(path) if path and self.job.folder_scope(path) else COMMON)
        self.refresh_preview()

    def refresh_preview(self, *_):
        if self.editor.currentWidget() is not self.preview:
            return
        item = self.tree.currentItem()
        path = item.data(0, ROLE) if item else None
        video = next((v for v in self.job.videos if v.path == path and v.eligible), None)
        self.preview.choose_video(video or self.reference_for(self.current_path))

    def load_scope(self, path, video):
        self.loaded = False
        self.current_path = path
        common = path == COMMON
        settings = self.job.common if common else self.job.folder_configs.get(path, self.job.overrides.get(path, self.job.common))
        self.editor.load(settings, video)
        self.editor.setEnabled(True)
        self.loaded = True
        self.add.setEnabled(True)
        self.reference_label.setText(('Fichier de référence : ' if common else 'Fichier : ') + Path(video.path).name)
        self.scope_text()
        self.refresh_batch()

    def reset_file(self):
        if self.current_path != COMMON:
            self.job.overrides.pop(self.current_path, None)
            video = self.known[self.current_path]
            self.load_scope(self.current_path, video)
            self.update_summary()

    def validate(self):
        self.save_current()
        self.sync_selection()
        self.job.output = self.output.text().strip()
        self.job.preserve_tree = True
        self.job.resume = self.resume.isChecked()
        self.job.dry_run = False
        try:
            self.job.commands()
        except ValueError as exc:
            QMessageBox.warning(self, 'Réglages à compléter', str(exc))
            return
        self.job.status = 'En attente'
        self.job.completed.clear()
        self.accept()
