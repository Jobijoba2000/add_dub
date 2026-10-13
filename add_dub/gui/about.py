"""Version and shipped notices, available from both graphical interfaces."""
from pathlib import Path
import sys
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QTextBrowser, QDialogButtonBox, QPushButton
from add_dub.gui.translations import ui
from add_dub.version import __version__


def show_about(parent=None):
    root = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[2]
    dialog = QDialog(parent)
    dialog.setWindowTitle(ui('À propos et licences'))
    dialog.resize(740, 560)
    layout = QVBoxLayout(dialog)
    title = QLabel(f'add_dub {__version__} · GNU GPLv3')
    title.setStyleSheet('font-size: 20px; font-weight: bold;')
    layout.addWidget(title)
    browser = QTextBrowser()
    browser.setOpenExternalLinks(True)
    browser.setSearchPaths([str(root), str(root / 'docs')])
    layout.addWidget(browser, 1)

    def notices():
        path = root / 'THIRD_PARTY_NOTICES.md'
        if path.is_file():
            browser.setMarkdown(path.read_text(encoding='utf-8'))
        else:
            browser.setPlainText(ui('Les notices sont disponibles dans THIRD_PARTY_NOTICES.md à côté de l’application.'))

    notices()
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    buttons.button(QDialogButtonBox.StandardButton.Close).setText(ui('Fermer'))
    buttons.rejected.connect(dialog.reject)
    license_button = QPushButton(ui('Licence du projet'))
    def project_license():
        path = root / 'LICENSE'
        if path.is_file():
            browser.setPlainText(path.read_text(encoding='utf-8'))
    license_button.clicked.connect(project_license)
    buttons.addButton(license_button, QDialogButtonBox.ButtonRole.ActionRole)
    notices_button = QPushButton(ui('Composants tiers'))
    notices_button.clicked.connect(notices)
    buttons.addButton(notices_button, QDialogButtonBox.ButtonRole.ActionRole)
    layout.addWidget(buttons)
    dialog.exec()
