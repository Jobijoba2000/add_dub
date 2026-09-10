"""Configuration d'un lot : détection, sélection et exceptions par vidéo."""
from copy import deepcopy
import os
from pathlib import Path
from functools import lru_cache

from PySide6.QtCore import Qt, QTimer, QFileInfo, QSignalBlocker
from PySide6.QtGui import QColor, QPixmap, QIcon
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QSplitter, QWidget, QLabel, QTreeWidget,
    QTreeWidgetItem, QPushButton, QCheckBox, QRadioButton, QButtonGroup,
    QLineEdit, QFileDialog, QMessageBox, QGroupBox, QStyle, QFileIconProvider, QProgressBar, QStyleFactory,
)
from add_dub.gui_model import discover, inspect_video, adapt_settings
from add_dub.gui_widgets import SettingsEditor

ROLE = Qt.ItemDataRole.UserRole
COMMON = '__common__'


@lru_cache(maxsize=2)
def yellow_folder_icon(opened):
    """Conserve les dessins Qt ouvert/fermé et leurs ombres, en jaune."""
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
        self.setWindowTitle('Configurer le doublage — add_dub')
        self.resize(1220, 850)
        self.setMinimumSize(860, 560)
        self.finished.connect(self.closed)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(22, 20, 22, 20)
        outer.setSpacing(14)
        heading = QLabel('Configurer les vidéos')
        heading.setObjectName('heading')
        outer.addWidget(heading)
        self.summary = QLabel('Recherche des vidéos…')
        self.summary.setWordWrap(True)
        outer.addWidget(self.summary)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(splitter, 1)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 8, 0)
        self.has_folders = any(os.path.isdir(p) for p in self.job.sources)
        self.scan_progress = QProgressBar()
        self.scan_progress.setObjectName('scanProgress')
        self.scan_progress.setAccessibleName('Progression de l’analyse des vidéos')
        self.scan_progress.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scan_progress.setFormat('%v/%m')
        left_layout.addWidget(self.scan_progress)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(['Fichiers', 'État'])
        self.tree.setAccessibleName('Sélection des vidéos et des dossiers')
        self.tree.setColumnWidth(0, 220)
        self.tree.setIconSize(QPixmap(28, 28).size())
        self.tree.setMinimumWidth(270)
        left_layout.addWidget(self.tree)
        left_hint = QLabel('Cochez les vidéos à traiter. Un dossier partiellement sélectionné porte une coche intermédiaire. Les vidéos sans sous-titres sont désactivées.')
        left_hint.setWordWrap(True)
        left_layout.addWidget(left_hint)
        splitter.addWidget(left)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 0, 0, 0)
        self.scope = QLabel()
        self.scope.setObjectName('scope')
        self.scope.setWordWrap(True)
        right_layout.addWidget(self.scope)
        self.reference_label = QLabel()
        self.reference_label.setWordWrap(True)
        right_layout.addWidget(self.reference_label)
        self.reset = QPushButton('Revenir aux réglages communs')
        self.reset.setAccessibleName('Supprimer les réglages personnalisés de cette vidéo')
        self.reset.clicked.connect(self.reset_file)
        right_layout.addWidget(self.reset, alignment=Qt.AlignmentFlag.AlignLeft)
        self.editor = SettingsEditor(tasks)
        self.editor.setEnabled(False)
        right_layout.addWidget(self.editor, 1)
        splitter.addWidget(right)
        splitter.setSizes([380, 800])
        output_row = QHBoxLayout()
        output_row.addWidget(QLabel('Dossier de sortie'))
        self.output = QLineEdit(self.job.output)
        self.output.setAccessibleName('Dossier de sortie du lot')
        output_row.addWidget(self.output, 1)
        browse = QPushButton('Parcourir…')
        browse.clicked.connect(self.choose_output)
        output_row.addWidget(browse)
        outer.addLayout(output_row)
        self.batch_options = QGroupBox('Options du lot')
        options = QVBoxLayout(self.batch_options)
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
        options.addLayout(policy_row)
        outer.addWidget(self.batch_options)
        footer = QHBoxLayout()
        self.dry_run = QCheckBox('Vérifier uniquement (sans produire de vidéo)')
        self.dry_run.setChecked(self.job.dry_run)
        footer.addWidget(self.dry_run)
        footer.addStretch()
        cancel = QPushButton('Annuler')
        cancel.clicked.connect(self.reject)
        footer.addWidget(cancel)
        self.add = QPushButton('Enregistrer les modifications' if job.videos else 'Ajouter à la liste d’attente')
        self.add.setObjectName('primary')
        self.add.setMinimumHeight(46)
        self.add.setEnabled(False)
        self.add.clicked.connect(self.validate)
        footer.addWidget(self.add)
        outer.addLayout(footer)
        self.tree.model().dataChanged.connect(self.tree_data_changed)
        self.tree.currentItemChanged.connect(self.select_item)
        self.tree.itemExpanded.connect(lambda item: self.set_folder_icon(item, True))
        self.tree.itemCollapsed.connect(lambda item: self.set_folder_icon(item, False))
        self.editor.changed.connect(self.edited)
        QTimer.singleShot(0, self.showMaximized)
        QTimer.singleShot(0, self.scan)

    def closed(self):
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
        common = self.current_path == COMMON
        if common:
            text = 'Réglages communs — appliqués à toutes les vidéos sans personnalisation.'
        else:
            custom = self.current_path in self.job.overrides
            text = ('Réglages personnalisés — ' if custom else 'Réglages communs adaptés à cette vidéo — ') + 'vos modifications ici ne concernent que ce fichier.'
        self.scope.setText(text)
        self.reset.setVisible(not common)
        for path, item in self.file_items.items():
            video = self.known.get(path)
            if video and video.eligible:
                item.setText(1, 'Personnalisé' if path in self.job.overrides else 'Commun')

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
            self.batch_options.setVisible(len(videos) > 1)
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
        common = QTreeWidgetItem(self.tree, ['Réglages communs du lot', ''])
        common.setData(0, ROLE, COMMON)
        folders = {}
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
        self.refresh_folders()
        self.tree.expandAll()
        # Les signaux sont bloqués pendant la construction : synchroniser aussi les icônes.
        for item in folders.values():
            self.set_folder_icon(item, item.isExpanded())
        self.tree.setCurrentItem(common)
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
        self.summary.setText(f'{len(self.job.selected)} vidéo(s) sélectionnée(s) sur {len(self.job.videos)} · {len(self.job.overrides)} personnalisation(s)')

    def select_item(self, item, previous):
        if not item:
            return
        path = item.data(0, ROLE)
        if not path:
            return
        self.save_current()
        self.detect_generation += 1
        generation = self.detect_generation
        if path == COMMON and self.reference:
            self.load_scope(COMMON, self.reference)
            return
        video = next((v for v in self.job.videos if v.path == path), None)
        if not video:
            return
        self.loaded = False
        self.editor.setEnabled(False)
        self.add.setEnabled(False)
        self.scope.setText(f'Actualisation des pistes — {Path(path).name}…')
        def done(updated, error):
            if generation != self.detect_generation:
                return
            if error:
                self.scope.setText(f'Détection impossible : {error}')
                return
            index = self.job.videos.index(video)
            item = self.file_items[path]
            updated.selected = updated.eligible and item.checkState(0) == Qt.CheckState.Checked
            self.job.videos[index] = updated
            self.known[path] = updated
            if not updated.eligible:
                self.build_tree()
                self.update_summary()
                self.scope.setText(updated.reason)
                return
            self.add.setEnabled(True)
            self.load_scope(path, updated)
        self.tasks.run(self, lambda: inspect_video(video), done)

    def load_scope(self, path, video):
        self.loaded = False
        self.current_path = path
        common = path == COMMON
        settings = self.job.common if common else self.job.overrides.get(path, self.job.common)
        self.editor.load(settings, video)
        self.editor.setEnabled(True)
        self.loaded = True
        self.add.setEnabled(True)
        self.reference_label.setText(('Fichier de référence : ' if common else 'Fichier : ') + Path(video.path).name)
        self.scope_text()

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
        self.job.dry_run = self.dry_run.isChecked()
        try:
            self.job.commands()
        except ValueError as exc:
            QMessageBox.warning(self, 'Réglages à compléter', str(exc))
            return
        self.job.status = 'En attente'
        self.job.completed.clear()
        self.accept()
