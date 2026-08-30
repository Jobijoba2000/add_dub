# add_dub/gui/qt_importer.py
from __future__ import annotations

import os
import tempfile
import threading
import winsound
from typing import List, Dict, Tuple, Optional, Any

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
    QPushButton,
    QComboBox,
    QSpinBox,
    QDoubleSpinBox,
    QCheckBox,
    QRadioButton,
    QButtonGroup,
    QTabWidget,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QFrame,
    QMessageBox,
)

import add_dub.io.fs as io_fs
from add_dub.adapters.ffmpeg import get_track_info
from add_dub.adapters.mkvtoolnix import list_mkv_sub_tracks
from add_dub.core.subtitles import find_sidecar_srt
from add_dub.core.options import DubOptions
from add_dub.core.tts_registry import normalize_engine, list_voices_for_engine
from add_dub.core.codecs import final_audio_codec_args, subtitle_codec_for_container

from add_dub.gui.qt_dialogs import (
    LANGUAGE_NAMES,
    REGION_NAMES,
    clean_voice_display_name,
)


def probe_video_sources(video_path: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Inspecte une vidéo (comme en mode CLI) pour lister toutes ses pistes audio et sous-titres.
    """
    audio_choices = []
    sub_choices = []

    # 1. Pistes audio via ffprobe
    try:
        streams = get_track_info(video_path)
        for idx, stream in enumerate(streams):
            ff_idx = stream.get("index")
            tags = stream.get("tags", {}) or {}
            lang = tags.get("language", "und")
            title = tags.get("title", "")
            codec = stream.get("codec_name", "")
            channels = stream.get("channels", 2)
            label = f"Piste {idx} (ffmpeg {ff_idx}) : {lang.upper()} — {codec} ({channels} ch){f' [{title}]' if title else ''}"
            audio_choices.append({
                "index": ff_idx,
                "label": label,
                "raw_idx": idx,
            })
    except Exception:
        pass

    if not audio_choices:
        audio_choices.append({"index": None, "label": "Piste 0 (Auto / Défaut)", "raw_idx": 0})

    # 2. Sources de sous-titres
    base_name = os.path.splitext(os.path.basename(video_path))[0]
    srt_in_srt = io_fs.join_srt(base_name + ".srt")
    has_srt_in_srt = os.path.exists(srt_in_srt)
    sidecar = find_sidecar_srt(video_path)

    if has_srt_in_srt:
        sub_choices.append({
            "type": "srt",
            "path": srt_in_srt,
            "label": f"Fichier SRT (dans srt/) : {os.path.basename(srt_in_srt)}",
            "choice": ("srt", srt_in_srt),
        })
    elif sidecar:
        sub_choices.append({
            "type": "srt",
            "path": sidecar,
            "label": f"Fichier SRT sidecar : {os.path.basename(sidecar)}",
            "choice": ("srt", sidecar),
        })

    _, ext = os.path.splitext(video_path)
    if ext.lower().endswith(".mkv"):
        try:
            mkv_tracks, printable = list_mkv_sub_tracks(video_path)
            for i, _t in enumerate(mkv_tracks):
                sub_choices.append({
                    "type": "mkv",
                    "index": i,
                    "label": f"Piste MKV intégrée {i} : {printable[i]}",
                    "choice": ("mkv", i),
                })
        except Exception:
            pass

    if not sub_choices:
        sub_choices.append({
            "type": "auto",
            "choice": None,
            "label": "Auto (Recherche automatique au moment du traitement)",
        })

    return audio_choices, sub_choices


class BatchImportDialog(QDialog):
    """
    Grande fenêtre de configuration de lot (ouverte à l'import de fichier/dossier).
    - Colonne gauche : liste des vidéos importées.
    - Colonne droite : 4 onglets de réglages (Pistes, Voix, Mixage, Traduction).
    - Bouton principal : Ajouter à la file d'attente.
    """
    def __init__(self, file_paths: List[str], base_settings: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuration du Lot de Vidéos — AdDub")
        self.resize(920, 620)
        self.setModal(True)

        self.file_paths = list(file_paths)
        self.settings = dict(base_settings)
        self.configured_items: List[Dict[str, Any]] = []

        self.regions_by_lang: Dict[str, List[Dict[str, str]]] = {}
        self.voices_by_region: Dict[str, List[Dict[str, str]]] = {}

        self.audio_choices, self.sub_choices = ([], [])
        if self.file_paths:
            self.audio_choices, self.sub_choices = probe_video_sources(self.file_paths[0])

        self._init_ui()
        self._load_voices(self.settings.get("tts_engine", "onecore"), self.settings.get("voice_id"))

    def _init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(14)

        # -------------------------------------------------------------
        # COLONNE DE GAUCHE : LISTE DES VIDÉOS DU LOT
        # -------------------------------------------------------------
        left_box = QGroupBox(f"Vidéos du lot ({len(self.file_paths)})")
        left_layout = QVBoxLayout(left_box)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(6)

        self.list_files = QListWidget()
        for p in self.file_paths:
            sz_mb = 0
            try:
                sz_mb = os.path.getsize(p) / (1024 * 1024)
            except Exception:
                pass
            item = QListWidgetItem(f"{os.path.basename(p)} ({sz_mb:.1f} Mo)")
            item.setToolTip(p)
            self.list_files.addItem(item)
        left_layout.addWidget(self.list_files)

        lbl_info = QLabel(f"Premier fichier inspecté :\n{os.path.basename(self.file_paths[0]) if self.file_paths else ''}")
        lbl_info.setStyleSheet("color: #888888; font-size: 11px;")
        lbl_info.setWordWrap(True)
        left_layout.addWidget(lbl_info)

        main_layout.addWidget(left_box, stretch=1)

        # -------------------------------------------------------------
        # COLONNE DE DROITE : 4 ONGLETS DE CONFIGURATION
        # -------------------------------------------------------------
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)

        tabs = QTabWidget()

        # --- ONGLET 1 : Pistes Audio & Sous-titres ---
        tab_tracks = QWidget()
        tab_tracks_layout = QVBoxLayout(tab_tracks)
        tab_tracks_layout.setSpacing(12)

        # GroupBox Pistes Audio
        grp_aud = QGroupBox("Choix de la piste audio d'origine (1 seul choix)")
        grp_aud_layout = QVBoxLayout(grp_aud)
        self.btn_group_audio = QButtonGroup(self)
        self.radio_audio_list = []

        for idx, item in enumerate(self.audio_choices):
            radio = QRadioButton(item["label"])
            self.btn_group_audio.addButton(radio, idx)
            grp_aud_layout.addWidget(radio)
            self.radio_audio_list.append(radio)
            if idx == 0:
                radio.setChecked(True)
        tab_tracks_layout.addWidget(grp_aud)

        # GroupBox Sous-titres
        grp_sub = QGroupBox("Choix de la source des sous-titres (1 seul choix)")
        grp_sub_layout = QVBoxLayout(grp_sub)
        self.btn_group_subs = QButtonGroup(self)
        self.radio_sub_list = []

        for idx, item in enumerate(self.sub_choices):
            radio = QRadioButton(item["label"])
            self.btn_group_subs.addButton(radio, idx)
            grp_sub_layout.addWidget(radio)
            self.radio_sub_list.append(radio)
            if idx == 0:
                radio.setChecked(True)
        tab_tracks_layout.addWidget(grp_sub)
        tab_tracks_layout.addStretch()
        tabs.addTab(tab_tracks, "1. Audio & Sous-titres")

        # --- ONGLET 2 : Voix ---
        tab_voice = QWidget()
        grid_voice = QGridLayout(tab_voice)
        grid_voice.setSpacing(10)

        grid_voice.addWidget(QLabel("Moteur de synthèse :"), 0, 0)
        self.combo_engine = QComboBox()
        self.combo_engine.addItem("OneCore (Hors-ligne Windows)", "onecore")
        self.combo_engine.addItem("Edge-TTS (En ligne)", "edge")
        self.combo_engine.addItem("Google TTS (En ligne)", "gtts")
        grid_voice.addWidget(self.combo_engine, 0, 1)

        grid_voice.addWidget(QLabel("Langue :"), 1, 0)
        self.combo_lang = QComboBox()
        grid_voice.addWidget(self.combo_lang, 1, 1)

        grid_voice.addWidget(QLabel("Région / Dialecte :"), 2, 0)
        self.combo_region = QComboBox()
        grid_voice.addWidget(self.combo_region, 2, 1)

        grid_voice.addWidget(QLabel("Voix :"), 3, 0)
        self.combo_voice = QComboBox()
        grid_voice.addWidget(self.combo_voice, 3, 1)

        self.btn_test = QPushButton("Tester la voix")
        self.btn_test.setMinimumHeight(32)
        grid_voice.addWidget(self.btn_test, 4, 1)

        grid_voice.addWidget(QLabel("Vitesse minimale (min_rate_tts) :"), 5, 0)
        self.spin_min_rate = QDoubleSpinBox()
        self.spin_min_rate.setRange(0.5, 3.0)
        self.spin_min_rate.setSingleStep(0.1)
        self.spin_min_rate.setValue(float(self.settings.get("min_rate_tts", 1.2)))
        grid_voice.addWidget(self.spin_min_rate, 5, 1)

        grid_voice.addWidget(QLabel("Vitesse maximale (max_rate_tts) :"), 6, 0)
        self.spin_max_rate = QDoubleSpinBox()
        self.spin_max_rate.setRange(0.5, 4.0)
        self.spin_max_rate.setSingleStep(0.1)
        self.spin_max_rate.setValue(float(self.settings.get("max_rate_tts", 1.8)))
        grid_voice.addWidget(self.spin_max_rate, 6, 1)

        tabs.addTab(tab_voice, "2. Voix")

        # --- ONGLET 3 : Mixage Audio ---
        tab_mix = QWidget()
        grid_mix = QGridLayout(tab_mix)
        grid_mix.setSpacing(10)

        grid_mix.addWidget(QLabel("Atténuation du fond (Ducking dB) :"), 0, 0)
        self.spin_ducking = QDoubleSpinBox()
        self.spin_ducking.setRange(-30.0, 0.0)
        self.spin_ducking.setSingleStep(1.0)
        self.spin_ducking.setValue(float(self.settings.get("ducking_db", -5.0)))
        grid_mix.addWidget(self.spin_ducking, 0, 1)

        grid_mix.addWidget(QLabel("Volume fond sonore (bg_mix) :"), 1, 0)
        self.spin_bg_mix = QDoubleSpinBox()
        self.spin_bg_mix.setRange(0.0, 2.0)
        self.spin_bg_mix.setSingleStep(0.1)
        self.spin_bg_mix.setValue(float(self.settings.get("bg_mix", 1.0)))
        grid_mix.addWidget(self.spin_bg_mix, 1, 1)

        grid_mix.addWidget(QLabel("Volume voix doublée (tts_mix) :"), 2, 0)
        self.spin_tts_mix = QDoubleSpinBox()
        self.spin_tts_mix.setRange(0.0, 2.0)
        self.spin_tts_mix.setSingleStep(0.1)
        self.spin_tts_mix.setValue(float(self.settings.get("tts_mix", 1.0)))
        grid_mix.addWidget(self.spin_tts_mix, 2, 1)

        grid_mix.addWidget(QLabel("Décalage voix / sous-titres (ms) :"), 3, 0)
        self.spin_offset_ms = QSpinBox()
        self.spin_offset_ms.setRange(-10000, 10000)
        self.spin_offset_ms.setSingleStep(50)
        self.spin_offset_ms.setValue(int(self.settings.get("offset_ms", 0)))
        grid_mix.addWidget(self.spin_offset_ms, 3, 1)

        grid_mix.addWidget(QLabel("Décalage vidéo (offset_video_ms) :"), 4, 0)
        self.spin_offset_vid = QSpinBox()
        self.spin_offset_vid.setRange(-10000, 10000)
        self.spin_offset_vid.setSingleStep(50)
        self.spin_offset_vid.setValue(int(self.settings.get("offset_video_ms", 0)))
        grid_mix.addWidget(self.spin_offset_vid, 4, 1)

        grid_mix.addWidget(QLabel("Codec audio final :"), 5, 0)
        self.combo_codec = QComboBox()
        self.combo_codec.addItem("AC3 (Recommandé MKV)", "ac3")
        self.combo_codec.addItem("AAC (Compatible MP4)", "aac")
        self.combo_codec.addItem("Opus (Haute fidélité)", "libopus")
        self.combo_codec.addItem("MP3", "mp3")
        self.combo_codec.addItem("FLAC (Sans perte)", "flac")
        self.combo_codec.addItem("PCM 16-bit WAV", "pcm_s16le")
        grid_mix.addWidget(self.combo_codec, 5, 1)

        grid_mix.addWidget(QLabel("Débit audio (kb/s) :"), 6, 0)
        self.combo_bitrate = QComboBox()
        for br in ["128", "160", "192", "224", "256", "320", "384", "448", "640"]:
            self.combo_bitrate.addItem(f"{br} kb/s", br)
        grid_mix.addWidget(self.combo_bitrate, 6, 1)

        tabs.addTab(tab_mix, "3. Mixage Audio")

        # --- ONGLET 4 : Traduction ---
        tab_trans = QWidget()
        grid_trans = QGridLayout(tab_trans)
        grid_trans.setSpacing(10)

        self.chk_translate = QCheckBox("Activer la traduction automatique des sous-titres")
        self.chk_translate.setChecked(bool(self.settings.get("translate", False)))
        grid_trans.addWidget(self.chk_translate, 0, 0, 1, 2)

        self.lbl_src_lang = QLabel("Langue source (De) :")
        grid_trans.addWidget(self.lbl_src_lang, 1, 0)
        self.txt_tr_from = QLineEdit(str(self.settings.get("translate_from", "auto")))
        grid_trans.addWidget(self.txt_tr_from, 1, 1)

        self.lbl_tgt_lang = QLabel("Langue cible (Vers) :")
        grid_trans.addWidget(self.lbl_tgt_lang, 2, 0)
        self.txt_tr_to = QLineEdit(str(self.settings.get("translate_to", "fr")))
        grid_trans.addWidget(self.txt_tr_to, 2, 1)

        self.chk_reuse_subs = QCheckBox("Réutiliser les sous-titres déjà traduits (dans srt/)")
        self.chk_reuse_subs.setChecked(bool(self.settings.get("reuse_translated_subs", True)))
        grid_trans.addWidget(self.chk_reuse_subs, 3, 0, 1, 2)

        grid_trans.setRowStretch(4, 1)
        tabs.addTab(tab_trans, "4. Traduction")

        right_layout.addWidget(tabs)

        # -------------------------------------------------------------
        # BOUTON PRINCIPAL EN BAS : AJOUTER À LA FILE D'ATTENTE
        # -------------------------------------------------------------
        btn_box = QHBoxLayout()
        btn_box.setSpacing(12)

        self.btn_cancel = QPushButton("Annuler")
        self.btn_cancel.setMinimumHeight(44)
        self.btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(self.btn_cancel)

        self.btn_add_to_queue = QPushButton(f"AJOUTER CES {len(self.file_paths)} VIDÉOS À LA FILE D'ATTENTE")
        self.btn_add_to_queue.setStyleSheet("""
            QPushButton {
                background-color: #0078D7;
                color: #FFFFFF;
                font-weight: 700;
                font-size: 14px;
                padding: 10px 20px;
                border-radius: 4px;
                border: 1px solid #0098FF;
            }
            QPushButton:hover {
                background-color: #1084E3;
            }
        """)
        self.btn_add_to_queue.setMinimumHeight(44)
        self.btn_add_to_queue.clicked.connect(self._on_accept)
        btn_box.addWidget(self.btn_add_to_queue, stretch=1)

        right_layout.addLayout(btn_box)
        main_layout.addWidget(right_container, stretch=2)

        # Connexions & Toggles
        self.combo_engine.currentIndexChanged.connect(self._on_engine_changed)
        self.combo_lang.currentIndexChanged.connect(self._on_lang_changed)
        self.combo_region.currentIndexChanged.connect(self._on_region_changed)
        self.btn_test.clicked.connect(self._on_test_voice)
        self.chk_translate.toggled.connect(self._on_translate_toggle)

        self._on_translate_toggle(self.chk_translate.isChecked())

        # Select initial values
        for i in range(self.combo_codec.count()):
            if self.combo_codec.itemData(i) == str(self.settings.get("audio_codec", "ac3")):
                self.combo_codec.setCurrentIndex(i)
                break

        cur_br = str(self.settings.get("audio_bitrate", "256")).replace("k", "")
        for i in range(self.combo_bitrate.count()):
            if self.combo_bitrate.itemData(i) == cur_br:
                self.combo_bitrate.setCurrentIndex(i)
                break

    def _on_translate_toggle(self, checked: bool):
        self.lbl_src_lang.setVisible(checked)
        self.txt_tr_from.setVisible(checked)
        self.lbl_tgt_lang.setVisible(checked)
        self.txt_tr_to.setVisible(checked)
        self.chk_reuse_subs.setVisible(checked)

    def _load_voices(self, engine: str, target_voice_id: Optional[str] = None):
        eng = normalize_engine(engine)
        for i in range(self.combo_engine.count()):
            if self.combo_engine.itemData(i) == eng:
                self.combo_engine.setCurrentIndex(i)
                break

        try:
            voices = list_voices_for_engine(eng)
        except Exception:
            voices = []

        lang_set = set()
        self.regions_by_lang = {}
        self.voices_by_region = {}
        seen_regions = set()

        for v in voices:
            loc = (v.get("lang") or "fr-FR").replace("_", "-")
            parts = loc.split("-")
            base_lang = parts[0].lower()
            region_code = parts[1].upper() if len(parts) > 1 else base_lang.upper()
            full_region = f"{base_lang}-{region_code}"

            lang_set.add(base_lang)
            if base_lang not in self.regions_by_lang:
                self.regions_by_lang[base_lang] = []

            if full_region not in seen_regions:
                seen_regions.add(full_region)
                reg_name = REGION_NAMES.get(region_code, region_code)
                self.regions_by_lang[base_lang].append({
                    "code": full_region,
                    "name": f"{reg_name} ({full_region})"
                })

            if full_region not in self.voices_by_region:
                self.voices_by_region[full_region] = []

            raw_disp = v.get("display_name") or v.get("id") or "Inconnue"
            clean_disp = clean_voice_display_name(raw_disp, v.get("id", ""))
            self.voices_by_region[full_region].append({
                "id": v.get("id", ""),
                "display_name": clean_disp,
                "lang": full_region
            })

        def lang_sort_key(code: str) -> tuple:
            if code == "fr":
                return (0, "")
            if code == "en":
                return (1, "")
            if code == "es":
                return (2, "")
            name = LANGUAGE_NAMES.get(code, code)
            return (3, name)

        sorted_lang_codes = sorted(list(lang_set), key=lang_sort_key)
        self.combo_lang.blockSignals(True)
        self.combo_lang.clear()

        fr_index = 0
        for idx, c in enumerate(sorted_lang_codes):
            name = f"{LANGUAGE_NAMES.get(c, c.upper())} ({c})"
            self.combo_lang.addItem(name, c)
            if c == "fr":
                fr_index = idx

        if self.combo_lang.count() > 0:
            self.combo_lang.setCurrentIndex(fr_index)
        self.combo_lang.blockSignals(False)

        self._on_lang_changed(target_voice_id=target_voice_id)

    def _on_engine_changed(self):
        engine = self.combo_engine.currentData()
        self._load_voices(engine)

    def _on_lang_changed(self, target_voice_id: Optional[str] = None):
        lang_code = self.combo_lang.currentData()
        regions = self.regions_by_lang.get(lang_code, [])

        self.combo_region.blockSignals(True)
        self.combo_region.clear()

        fr_reg_idx = 0
        for idx, r in enumerate(regions):
            self.combo_region.addItem(r["name"], r["code"])
            if r["code"] in ("fr-FR", "en-US", f"{lang_code}-{lang_code.upper()}"):
                fr_reg_idx = idx

        if self.combo_region.count() > 0:
            self.combo_region.setCurrentIndex(fr_reg_idx)
        self.combo_region.blockSignals(False)

        self._on_region_changed(target_voice_id=target_voice_id)

    def _on_region_changed(self, target_voice_id: Optional[str] = None):
        region_code = self.combo_region.currentData()
        voices = self.voices_by_region.get(region_code, [])

        self.combo_voice.blockSignals(True)
        self.combo_voice.clear()

        target_idx = 0
        for idx, v in enumerate(voices):
            self.combo_voice.addItem(v["display_name"], v["id"])
            if target_voice_id and v["id"] == target_voice_id:
                target_idx = idx

        if self.combo_voice.count() > 0:
            self.combo_voice.setCurrentIndex(target_idx)
        self.combo_voice.blockSignals(False)

    def _on_test_voice(self):
        engine = self.combo_engine.currentData()
        voice_id = self.combo_voice.currentData()
        region = self.combo_region.currentData() or "fr-FR"
        min_rate = self.spin_min_rate.value()
        max_rate = self.spin_max_rate.value()

        self.btn_test.setEnabled(False)
        self.btn_test.setText("Génération...")

        def _worker():
            try:
                opts = DubOptions(
                    tts_engine=engine,
                    voice_id=voice_id,
                    min_rate_tts=min_rate,
                    max_rate_tts=max_rate,
                )
                text = "Bonjour, ceci est un test de la voix pour le doublage automatique."
                if engine == "onecore":
                    from add_dub.core.tts import synthesize_tts_for_subtitle
                    seg = synthesize_tts_for_subtitle(text, 3500, voice_id, opts)
                elif engine == "edge":
                    from add_dub.core.tts_edge import synthesize_tts_for_subtitle
                    seg = synthesize_tts_for_subtitle(text, 3500, voice_id, opts)
                else:
                    from add_dub.core.tts_gtts import synthesize_tts_for_subtitle
                    seg = synthesize_tts_for_subtitle(text, 3500, region[:2], opts)

                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    tmp_wav = f.name
                seg.export(tmp_wav, format="wav")
                winsound.PlaySound(tmp_wav, winsound.SND_FILENAME)
                try:
                    os.remove(tmp_wav)
                except Exception:
                    pass
            except Exception:
                pass
            finally:
                self.btn_test.setEnabled(True)
                self.btn_test.setText("Tester la voix")

        threading.Thread(target=_worker, daemon=True).start()

    def _on_accept(self):
        # Récupération du choix audio
        chosen_aud_idx = self.btn_group_audio.checkedId()
        audio_choice_item = self.audio_choices[chosen_aud_idx] if 0 <= chosen_aud_idx < len(self.audio_choices) else self.audio_choices[0]

        # Récupération du choix sous-titre
        chosen_sub_idx = self.btn_group_subs.checkedId()
        sub_choice_item = self.sub_choices[chosen_sub_idx] if 0 <= chosen_sub_idx < len(self.sub_choices) else self.sub_choices[0]

        batch_settings = {
            "audio_ffmpeg_index": audio_choice_item.get("index"),
            "audio_label": audio_choice_item.get("label"),
            "sub_choice": sub_choice_item.get("choice"),
            "sub_label": sub_choice_item.get("label"),
            "tts_engine": self.combo_engine.currentData(),
            "voice_lang": self.combo_region.currentData() or self.combo_lang.currentData() or "fr-FR",
            "voice_id": self.combo_voice.currentData(),
            "voice_display_name": self.combo_voice.currentText(),
            "min_rate_tts": self.spin_min_rate.value(),
            "max_rate_tts": self.spin_max_rate.value(),
            "ducking_db": self.spin_ducking.value(),
            "bg_mix": self.spin_bg_mix.value(),
            "tts_mix": self.spin_tts_mix.value(),
            "offset_ms": self.spin_offset_ms.value(),
            "offset_video_ms": self.spin_offset_vid.value(),
            "audio_codec": self.combo_codec.currentData(),
            "audio_bitrate": self.combo_bitrate.currentData(),
            "translate": self.chk_translate.isChecked(),
            "translate_from": self.txt_tr_from.text().strip() if self.chk_translate.isChecked() else "auto",
            "translate_to": self.txt_tr_to.text().strip() if self.chk_translate.isChecked() else "fr",
            "reuse_translated_subs": self.chk_reuse_subs.isChecked(),
        }

        self.configured_items = []
        for p in self.file_paths:
            self.configured_items.append({
                "path": p,
                "settings": dict(batch_settings),
            })

        self.accept()
