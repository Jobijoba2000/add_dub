# add_dub/gui/qt_dialogs.py
from __future__ import annotations

import os
import re
import tempfile
import threading
import winsound
from typing import Dict, List, Optional, Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QComboBox,
    QSpinBox,
    QDoubleSpinBox,
    QCheckBox,
    QPushButton,
    QDialogButtonBox,
    QMessageBox,
    QTabWidget,
)

from add_dub.core.tts_registry import normalize_engine, list_voices_for_engine
from add_dub.core.options import DubOptions
from add_dub.config.opts_loader import save_option


LANGUAGE_NAMES: Dict[str, str] = {
    "fr": "Français",
    "en": "Anglais",
    "es": "Espagnol",
    "de": "Allemand",
    "it": "Italien",
    "pt": "Portugais",
    "ja": "Japonais",
    "zh": "Chinois",
    "ru": "Russe",
    "ar": "Arabe",
    "nl": "Néerlandais",
    "pl": "Polonais",
    "ko": "Coréen",
    "tr": "Turc",
    "uk": "Ukrainien",
    "sv": "Suédois",
    "cs": "Tchèque",
    "el": "Grec",
    "da": "Danois",
    "fi": "Finnois",
    "no": "Norvégien",
    "hi": "Hindi",
    "vi": "Vietnamien",
    "id": "Indonésien",
    "th": "Thaï",
    "ro": "Roumain",
    "hu": "Hongrois",
}

REGION_NAMES: Dict[str, str] = {
    "FR": "France",
    "CA": "Canada",
    "BE": "Belgique",
    "CH": "Suisse",
    "US": "États-Unis",
    "GB": "Royaume-Uni",
    "AU": "Australie",
    "ES": "Espagne",
    "MX": "Mexique",
    "DE": "Allemagne",
    "AT": "Autriche",
    "IT": "Italie",
    "BR": "Brésil",
    "PT": "Portugal",
    "JP": "Japon",
    "CN": "Chine",
    "TW": "Taïwan",
    "RU": "Russie",
    "IN": "Inde",
    "NL": "Pays-Bas",
    "PL": "Pologne",
    "KR": "Corée",
    "TR": "Turquie",
    "UA": "Ukraine",
    "SE": "Suède",
    "CZ": "Tchéquie",
    "GR": "Grèce",
    "DK": "Danemark",
    "FI": "Finlande",
    "NO": "Norvège",
    "RO": "Roumanie",
    "HU": "Hongrie",
    "VN": "Vietnam",
    "ID": "Indonésie",
    "TH": "Thaïlande",
    "SA": "Arabie Saoudite",
    "EG": "Égypte",
}


def clean_voice_display_name(raw_disp: str, vid: str) -> str:
    m = re.search(r'\((?:[a-zA-Z\-]+,\s*)?([a-zA-Z0-9]+)\)', raw_disp)
    if m:
        name = m.group(1)
    else:
        name = raw_disp or vid
    name = re.sub(r'Neural$', ' (Neural)', name)
    name = re.sub(r'Multilingual', ' Multilingual', name)
    return name.strip()


class ConflictDialog(QDialog):
    """
    Boîte de dialogue modale lors d'un conflit de fichier existant en sortie.
    Propose 4 choix : Oui, Oui pour tous, Non, Non pour tous.
    """
    def __init__(self, filename: str, output_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Fichier déjà existant — Conflit")
        self.setMinimumWidth(480)
        self.setModal(True)

        self.choice_result = "no"

        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        msg_label = QLabel(
            f"<b>Le fichier de sortie existe déjà :</b><br><br>"
            f"<code>{os.path.basename(output_path)}</code><br><br>"
            f"Voulez-vous écraser ce fichier ou ignorer son traitement ?"
        )
        msg_label.setWordWrap(True)
        layout.addWidget(msg_label)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        btn_yes = QPushButton("Oui (Écraser)")
        btn_yes.clicked.connect(lambda: self._set_choice("yes"))
        btn_layout.addWidget(btn_yes)

        btn_yes_all = QPushButton("Oui pour tous")
        btn_yes_all.clicked.connect(lambda: self._set_choice("yes_all"))
        btn_layout.addWidget(btn_yes_all)

        btn_no = QPushButton("Non (Ignorer)")
        btn_no.clicked.connect(lambda: self._set_choice("no"))
        btn_layout.addWidget(btn_no)

        btn_no_all = QPushButton("Non pour tous")
        btn_no_all.clicked.connect(lambda: self._set_choice("no_all"))
        btn_layout.addWidget(btn_no_all)

        layout.addLayout(btn_layout)

    def _set_choice(self, choice: str):
        self.choice_result = choice
        self.accept()


class DefaultSettingsDialog(QDialog):
    """
    Dialogue des paramètres généraux et valeurs par défaut (sauvegardées dans options.conf).
    """
    def __init__(self, base_settings: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Paramètres par Défaut (options.conf)")
        self.resize(600, 480)
        self.setModal(True)

        self.settings = dict(base_settings)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        tabs = QTabWidget()

        # Onglet 1 : Dossiers & Général
        tab_gen = QWidget()
        grid_gen = QGridLayout(tab_gen)
        grid_gen.setSpacing(10)

        grid_gen.addWidget(QLabel("Dossier de sortie par défaut :"), 0, 0)
        self.txt_out_dir = QLineEdit(str(self.settings.get("output_dir", "output")))
        grid_gen.addWidget(self.txt_out_dir, 0, 1)

        grid_gen.addWidget(QLabel("Langue de l'interface :"), 1, 0)
        self.combo_app_lang = QComboBox()
        self.combo_app_lang.addItem("Français (fr)", "fr")
        self.combo_app_lang.addItem("English (en)", "en")
        self.combo_app_lang.addItem("Español (es)", "es")
        self.combo_app_lang.addItem("Deutsch (de)", "de")
        grid_gen.addWidget(self.combo_app_lang, 1, 1)

        self.chk_preserve_tree = QCheckBox("Conserver l'arborescence des dossiers (--preserve-tree)")
        self.chk_preserve_tree.setChecked(bool(self.settings.get("preserve_tree", False)))
        grid_gen.addWidget(self.chk_preserve_tree, 2, 0, 1, 2)

        grid_gen.setRowStretch(3, 1)
        tabs.addTab(tab_gen, "1. Général & Dossiers")

        # Onglet 2 : Synthèse Vocale
        tab_tts = QWidget()
        grid_tts = QGridLayout(tab_tts)
        grid_tts.setSpacing(10)

        grid_tts.addWidget(QLabel("Moteur TTS par défaut :"), 0, 0)
        self.combo_engine = QComboBox()
        self.combo_engine.addItem("OneCore (Hors-ligne)", "onecore")
        self.combo_engine.addItem("Edge-TTS (En ligne)", "edge")
        self.combo_engine.addItem("Google TTS (En ligne)", "gtts")
        grid_tts.addWidget(self.combo_engine, 0, 1)

        grid_tts.addWidget(QLabel("Vitesse minimale (min_rate_tts) :"), 1, 0)
        self.spin_min_rate = QDoubleSpinBox()
        self.spin_min_rate.setRange(0.5, 3.0)
        self.spin_min_rate.setSingleStep(0.1)
        self.spin_min_rate.setValue(float(self.settings.get("min_rate_tts", 1.2)))
        grid_tts.addWidget(self.spin_min_rate, 1, 1)

        grid_tts.addWidget(QLabel("Vitesse maximale (max_rate_tts) :"), 2, 0)
        self.spin_max_rate = QDoubleSpinBox()
        self.spin_max_rate.setRange(0.5, 4.0)
        self.spin_max_rate.setSingleStep(0.1)
        self.spin_max_rate.setValue(float(self.settings.get("max_rate_tts", 1.8)))
        grid_tts.addWidget(self.spin_max_rate, 2, 1)

        grid_tts.setRowStretch(3, 1)
        tabs.addTab(tab_tts, "2. Synthèse Vocale")

        # Onglet 3 : Mixage Audio
        tab_mix = QWidget()
        grid_mix = QGridLayout(tab_mix)
        grid_mix.setSpacing(10)

        grid_mix.addWidget(QLabel("Ducking par défaut (dB) :"), 0, 0)
        self.spin_ducking = QDoubleSpinBox()
        self.spin_ducking.setRange(-30.0, 0.0)
        self.spin_ducking.setSingleStep(1.0)
        self.spin_ducking.setValue(float(self.settings.get("ducking_db", -5.0)))
        grid_mix.addWidget(self.spin_ducking, 0, 1)

        grid_mix.addWidget(QLabel("Volume fond sonore (bg_mix) :"), 1, 0)
        self.spin_bg = QDoubleSpinBox()
        self.spin_bg.setRange(0.0, 2.0)
        self.spin_bg.setSingleStep(0.1)
        self.spin_bg.setValue(float(self.settings.get("bg_mix", 1.0)))
        grid_mix.addWidget(self.spin_bg, 1, 1)

        grid_mix.addWidget(QLabel("Volume voix doublée (tts_mix) :"), 2, 0)
        self.spin_tts = QDoubleSpinBox()
        self.spin_tts.setRange(0.0, 2.0)
        self.spin_tts.setSingleStep(0.1)
        self.spin_tts.setValue(float(self.settings.get("tts_mix", 1.0)))
        grid_mix.addWidget(self.spin_tts, 2, 1)

        grid_mix.addWidget(QLabel("Codec audio final :"), 3, 0)
        self.combo_codec = QComboBox()
        self.combo_codec.addItem("AC3 (Recommandé MKV)", "ac3")
        self.combo_codec.addItem("AAC (Compatible MP4)", "aac")
        self.combo_codec.addItem("Opus (Haute fidélité)", "libopus")
        self.combo_codec.addItem("MP3", "mp3")
        self.combo_codec.addItem("FLAC (Sans perte)", "flac")
        self.combo_codec.addItem("PCM 16-bit WAV", "pcm_s16le")
        grid_mix.addWidget(self.combo_codec, 3, 1)

        grid_mix.addWidget(QLabel("Débit audio (kb/s) :"), 4, 0)
        self.combo_bitrate = QComboBox()
        for br in ["128", "160", "192", "224", "256", "320", "384", "448", "640"]:
            self.combo_bitrate.addItem(f"{br} kb/s", br)
        grid_mix.addWidget(self.combo_bitrate, 4, 1)

        grid_mix.setRowStretch(5, 1)
        tabs.addTab(tab_mix, "3. Mixage Audio")

        layout.addWidget(tabs)

        # Boutons OK / Annuler
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Select initial values
        for i in range(self.combo_engine.count()):
            if self.combo_engine.itemData(i) == str(self.settings.get("tts_engine", "onecore")):
                self.combo_engine.setCurrentIndex(i)
                break

        for i in range(self.combo_codec.count()):
            if self.combo_codec.itemData(i) == str(self.settings.get("audio_codec", "ac3")):
                self.combo_codec.setCurrentIndex(i)
                break

        cur_br = str(self.settings.get("audio_bitrate", "256")).replace("k", "")
        for i in range(self.combo_bitrate.count()):
            if self.combo_bitrate.itemData(i) == cur_br:
                self.combo_bitrate.setCurrentIndex(i)
                break

    def _on_accept(self):
        # Sauvegarde persistante dans options.conf
        save_option("output_dir", self.txt_out_dir.text().strip())
        save_option("language", self.combo_app_lang.currentData())
        save_option("preserve_tree", self.chk_preserve_tree.isChecked())
        save_option("tts_engine", self.combo_engine.currentData())
        save_option("min_rate_tts", self.spin_min_rate.value())
        save_option("max_rate_tts", self.spin_max_rate.value())
        save_option("db", self.spin_ducking.value())
        save_option("bg", self.spin_bg.value())
        save_option("tts", self.spin_tts.value())
        save_option("audio_codec", self.combo_codec.currentData())
        save_option("audio_bitrate", int(self.combo_bitrate.currentData()))

        self.settings["output_dir"] = self.txt_out_dir.text().strip()
        self.settings["preserve_tree"] = self.chk_preserve_tree.isChecked()
        self.settings["tts_engine"] = self.combo_engine.currentData()
        self.settings["min_rate_tts"] = self.spin_min_rate.value()
        self.settings["max_rate_tts"] = self.spin_max_rate.value()
        self.settings["ducking_db"] = self.spin_ducking.value()
        self.settings["bg_mix"] = self.spin_bg.value()
        self.settings["tts_mix"] = self.spin_tts.value()
        self.settings["audio_codec"] = self.combo_codec.currentData()
        self.settings["audio_bitrate"] = self.combo_bitrate.currentData()

        QMessageBox.information(self, "Sauvegardé", "Les paramètres par défaut ont été enregistrés dans options.conf.")
        self.accept()
