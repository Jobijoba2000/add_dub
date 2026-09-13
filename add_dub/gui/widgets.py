"""Widgets Qt accessibles et chargement asynchrone des catalogues de voix."""
from copy import deepcopy
import threading

from PySide6.QtCore import QObject, Signal, QLocale, Qt, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPainter, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QComboBox, QLabel, QCheckBox, QRadioButton, QButtonGroup,
    QLineEdit, QTabWidget, QScrollArea, QSpinBox, QDoubleSpinBox, QTreeWidget, QAbstractItemView, QScroller, QMenu, QTabBar,
    QStylePainter, QStyleOptionTab, QStyle, QStyleOptionButton, QSizePolicy, QPushButton, QHBoxLayout, QAbstractSpinBox,
)
from shiboken6 import isValid
from add_dub.gui.model import FIELDS, Settings, adapt_settings


class ConfigButton(QPushButton):
    """Bouton capsule dont le dessin est indépendant du style natif Windows."""
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        selected = self.isChecked()
        painter.setBrush(QColor('#505050' if selected else '#222222'))
        painter.setPen(QColor('#ffffff' if self.underMouse() or self.hasFocus() else '#b0b0b0' if selected else '#606060'))
        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        painter.setPen(QColor('#f0f0f0' if selected else '#aaaaaa'))
        font = self.font()
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.text())


class QueueTabBar(QTabBar):
    """Prolonge la bordure de la liste en laissant l’onglet actif ouvert."""
    def tabSizeHint(self, index):
        # Le thème réserve la largeur en gras pour tous les onglets ;
        # paintEvent ne dessine en gras que celui qui est sélectionné.
        size = super().tabSizeHint(index)
        if self.count():
            size.setWidth(max(super(QueueTabBar, self).tabSizeHint(i).width() for i in range(self.count())))
        size.setHeight(max(size.height(), self.fontMetrics().height() + 22))
        return size

    def paintEvent(self, event):
        painter = QStylePainter(self)
        for index in range(self.count()):
            option = QStyleOptionTab()
            self.initStyleOption(option, index)
            painter.drawControl(QStyle.ControlElement.CE_TabBarTabShape, option)
            # Centrer dans la même zone pour les deux états, indépendamment
            # des décalages de libellé appliqués par le style natif.
            font = self.font()
            font.setBold(index == self.currentIndex())
            painter.setFont(font)
            painter.setPen(QColor('#ffffff' if index == self.currentIndex() else '#eeeeee'))
            text_rect = self.tabRect(index).adjusted(1, 1, -9, 0)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, self.tabText(index))
            if self.hasFocus() and index == self.currentIndex():
                painter.setPen(QColor('#ffdf00'))
                painter.drawRect(text_rect.adjusted(4, 4, -4, -4))
        painter.setPen(QColor('#858585'))
        y = self.height() - 1
        active = self.tabRect(self.currentIndex())
        if active.isValid():
            if active.left() > 0:
                painter.drawLine(0, y, active.left(), y)
            # La marge droite des onglets vaut 8 pixels dans le thème.
            painter.drawLine(active.right() - 8, y, self.width() - 1, y)
        else:
            painter.drawLine(0, y, self.width() - 1, y)
        painter.end()


class SpacedMenu(QMenu):
    """Garde un espace avec le bouton, y compris près du bord de l’écran."""
    def showEvent(self, event):
        self.setMinimumWidth(max(260, self.fontMetrics().horizontalAdvance('Ouvrir des vidéos…') + 110))
        super().showEvent(event)
        bounds = self.screen().availableGeometry()
        y = self.y() + 8
        if y + self.height() > bounds.bottom() + 1:
            y = self.y() - 8
        self.move(self.x(), max(bounds.top(), y))


class SmoothScrollMixin:
    def __init__(self, parent=None):
        super().__init__(parent)
        self._scroll = QPropertyAnimation(self.verticalScrollBar(), b'value', self)
        self._scroll.setDuration(220)
        self._scroll.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.verticalScrollBar().sliderPressed.connect(self._scroll.stop)
        QScroller.grabGesture(self.viewport(), QScroller.ScrollerGestureType.TouchGesture)

    def wheelEvent(self, event):
        if event.modifiers() or event.angleDelta().x():
            return super().wheelEvent(event)
        bar = self.verticalScrollBar()
        pixel = event.pixelDelta().y()
        if pixel:
            self._scroll.stop()
            bar.setValue(bar.value() - pixel)
        else:
            target = self._scroll.endValue() if self._scroll.state() == QPropertyAnimation.State.Running else bar.value()
            target = max(bar.minimum(), min(bar.maximum(), int(target - event.angleDelta().y())))
            self._scroll.stop()
            self._scroll.setStartValue(bar.value())
            self._scroll.setEndValue(target)
            self._scroll.start()
        event.accept()


class SmoothTreeWidget(SmoothScrollMixin, QTreeWidget):
    def drawRow(self, painter, option, index):
        super().drawRow(painter, option, index)
        if (self.objectName() == 'configurationFiles'
                and index.siblingAtColumn(0).data(Qt.ItemDataRole.UserRole + 8)
                != getattr(self, 'active_config_scope', None)):
            painter.save()
            rect = option.rect.adjusted(0, 0, 0, 0)
            rect.setLeft(0)
            rect.setRight(self.viewport().width())
            painter.fillRect(rect, QColor(0, 0, 0, 110))
            painter.restore()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)


class SmoothScrollArea(SmoothScrollMixin, QScrollArea):
    pass


class Async(QObject):
    delivered = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.delivered.connect(self.deliver)

    def deliver(self, event):
        owner, callback, result, error = event
        if isValid(owner) and not getattr(owner, '_closed', False):
            callback(result, error)

    def run(self, owner, function, callback, progress=None):
        def report(value):
            if isValid(self):
                self.delivered.emit((owner, lambda result, error: progress(result), value, None))

        def work():
            result, error = None, None
            try:
                result = function(report) if progress is not None else function()
            except Exception as exc:
                error = str(exc)
            if isValid(self):
                self.delivered.emit((owner, callback, result, error))
        threading.Thread(target=work, daemon=True).start()


def combo(entries=(), name=''):
    box = QComboBox()
    box.setMinimumContentsLength(18)
    box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    box.setAccessibleName(name)
    for label, value in entries:
        box.addItem(label, value)
    return box


def choose(box, value):
    index = box.findData(value)
    box.setCurrentIndex(index if index >= 0 else (0 if box.count() else -1))


def page_form(tabs, title):
    content = QWidget()
    form = QFormLayout(content)
    form.setContentsMargins(24, 26, 24, 26)
    form.setVerticalSpacing(24)
    form.setHorizontalSpacing(30)
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
    form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
    scroll = SmoothScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setWidget(content)
    tabs.addTab(scroll, title)
    return form


class VoicePicker(QWidget):
    changed = Signal()

    def __init__(self, async_tasks, parent=None, form=None):
        super().__init__(parent)
        self.tasks = async_tasks
        self.cache = {}
        self.voices = []
        self.desired = ''
        self.preferred_language = 'fr'
        self.preferred_region = QLocale.system().name().replace('_', '-')
        self.generation = 0
        self.loading = False
        if form is None:
            form = QFormLayout(self)
            form.setContentsMargins(0, 0, 0, 0)
            form.setVerticalSpacing(14)
            form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.engine = combo([('Windows OneCore · hors ligne', 'onecore'), ('Edge · en ligne', 'edge'), ('Google TTS · en ligne', 'gtts')], 'Moteur vocal')
        self.language = combo(name='Langue de la voix')
        self.region = combo(name='Variante régionale')
        self.voice = combo(name='Voix disponible')
        for label, widget in (('Moteur', self.engine), ('Langue', self.language), ('Région', self.region), ('Voix', self.voice)):
            form.addRow(label, widget)
        self.notice = QLabel()
        self.notice.setWordWrap(True)
        form.addRow(self.notice)
        self.engine.currentIndexChanged.connect(self.engine_changed)
        self.language.currentIndexChanged.connect(self.language_changed)
        self.region.currentIndexChanged.connect(self.region_changed)
        self.voice.currentIndexChanged.connect(self.changed)

    def set_value(self, engine, voice, preferred='fr'):
        self.preferred_language = preferred or 'fr'
        # La région par défaut suit la locale Windows. Elle ne sera remplacée
        # que si une voix précise est déjà sélectionnée.
        self.preferred_region = QLocale.system().name().replace('_', '-')
        self.desired = voice or ''
        self.engine.blockSignals(True)
        choose(self.engine, engine)
        self.engine.blockSignals(False)
        self.load()

    def engine_changed(self):
        self.desired = ''
        self.load()
        self.changed.emit()

    def load(self):
        engine = self.engine.currentData()
        self.generation += 1
        generation = self.generation
        self.loading = True
        for box in (self.language, self.region, self.voice):
            box.blockSignals(True)
            box.clear()
            box.setEnabled(False)
            box.blockSignals(False)
        self.notice.setText('Recherche des langues et des voix…')
        def finish(voices, error):
            if generation != self.generation:
                return
            self.loading = False
            self.voices = voices or []
            if self.voices:
                self.cache[engine] = self.voices
            self.populate(error)
        if engine in self.cache:
            finish(self.cache[engine], None)
        else:
            def fetch():
                from add_dub.core.tts_registry import list_voices_for_engine
                return list_voices_for_engine(engine)
            self.tasks.run(self, fetch, finish)

    def populate(self, error):
        self.language.blockSignals(True)
        languages = sorted({v.get('lang', '').replace('_', '-').split('-')[0] for v in self.voices})
        for code in languages:
            locale = QLocale(code)
            label = locale.nativeLanguageName() or code or 'Langue inconnue'
            self.language.addItem(f'{label.capitalize()} ({code})', code)
        desired = next((v for v in self.voices if v['id'] == self.desired), None)
        code = desired['lang'].replace('_', '-').split('-')[0] if desired else self.preferred_language.split('-')[0]
        choose(self.language, code)
        self.language.setEnabled(bool(languages))
        self.language.blockSignals(False)
        self.language_changed()
        if error or not self.voices:
            self.notice.setText(error or 'Aucune voix disponible. Choisissez un autre moteur ou installez une voix Windows.')
        elif self.engine.currentData() == 'gtts':
            self.notice.setText('gTTS propose une voix par langue, sans choix de timbre.')
        elif self.engine.currentData() == 'edge' and len(self.voices) == 1:
            self.notice.setText('Catalogue Edge limité : connexion indisponible, voix de secours proposée.')
        else:
            self.notice.setText(f'{len(self.voices)} voix détectées pour ce moteur.')

    def language_changed(self):
        code = self.language.currentData()
        self.region.blockSignals(True)
        self.region.clear()
        locales = sorted({v.get('lang', '') for v in self.voices if v.get('lang', '').replace('_', '-').split('-')[0] == code})
        for locale_code in locales:
            locale = QLocale(locale_code)
            name = locale.nativeTerritoryName() if '-' in locale_code or '_' in locale_code else 'Variante unique'
            self.region.addItem(f'{name or locale_code} ({locale_code})', locale_code)
        desired = next((v for v in self.voices if v['id'] == self.desired), None)
        if desired:
            choose(self.region, desired['lang'])
        else:
            choose(self.region, self.preferred_region)
        self.region.setEnabled(len(locales) > 1)
        self.region.blockSignals(False)
        self.region_changed()

    def region_changed(self):
        self.voice.blockSignals(True)
        self.voice.clear()
        for record in self.voices:
            if record.get('lang', '') == self.region.currentData():
                self.voice.addItem(record.get('display_name') or record['id'], record['id'])
        choose(self.voice, self.desired)
        self.voice.setEnabled(self.voice.count() > 0)
        self.voice.blockSignals(False)
        self.changed.emit()

    def value(self):
        return self.engine.currentData(), (self.desired if self.loading else self.voice.currentData()) or ''


class TrackRadioButton(QRadioButton):
    """Conserve le libellé accessible complet sans imposer sa largeur."""

    def minimumSizeHint(self):
        size = super().minimumSizeHint()
        size.setWidth(80)
        return size

    def sizeHint(self):
        size = super().sizeHint()
        size.setWidth(min(size.width(), 360))
        return size

    def paintEvent(self, event):
        option = QStyleOptionButton()
        self.initStyleOption(option)
        indicator = self.style().pixelMetric(QStyle.PixelMetric.PM_ExclusiveIndicatorWidth)
        spacing = self.style().pixelMetric(QStyle.PixelMetric.PM_RadioButtonLabelSpacing)
        option.text = self.fontMetrics().elidedText(
            self.text(), Qt.TextElideMode.ElideRight, max(0, self.width() - indicator - spacing - 8))
        painter = QStylePainter(self)
        painter.drawControl(QStyle.ControlElement.CE_RadioButton, option)


class TrackPicker(QWidget):
    """Sélecteur de piste accessible avec des boutons radio explicites."""
    currentIndexChanged = Signal(int)

    def __init__(self, accessible_name='', parent=None):
        super().__init__(parent)
        self.setAccessibleName(accessible_name)
        self.group = QButtonGroup(self)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(12)
        self._values = []
        self.group.idClicked.connect(self.currentIndexChanged)

    def clear(self):
        for button in self.group.buttons():
            self.group.removeButton(button)
            self.layout.removeWidget(button)
            button.hide()
            button.deleteLater()
        self._values.clear()

    def addItem(self, label, value):
        index = len(self._values)
        button = TrackRadioButton(label, self)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        button.setToolTip(label)
        self.group.addButton(button, index)
        self.layout.addWidget(button)
        self._values.append(value)
        if index == 0:
            button.setChecked(True)

    def currentData(self):
        index = self.group.checkedId()
        return self._values[index] if 0 <= index < len(self._values) else None

    def findData(self, value):
        try:
            return self._values.index(value)
        except ValueError:
            return -1

    def count(self):
        return len(self._values)

    def currentText(self):
        button = self.group.checkedButton()
        return button.text() if button else ''

    def setCurrentIndex(self, index):
        button = self.group.button(index)
        if button:
            button.setChecked(True)


class SettingsEditor(QTabWidget):
    changed = Signal()

    def __init__(self, tasks, parent=None):
        super().__init__(parent)
        self.loading = False
        self.base = None
        self.video = None
        self.setAccessibleName('Réglages du doublage')
        self.setObjectName('settingsTabs')
        tab_bar = QueueTabBar(self)
        tab_bar.setObjectName('queueTabs')
        tab_bar.setExpanding(False)
        tab_bar.setDrawBase(False)
        self.setTabBar(tab_bar)
        sources = page_form(self, 'Pistes')
        sources.setVerticalSpacing(32)
        sources.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        sources.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        sources.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.audio = TrackPicker('Piste audio originale')
        self.sub = TrackPicker('Source des sous-titres')
        sources.addRow('Audio original', self.audio)
        sources.addRow('Sous-titres', self.sub)
        voices = page_form(self, 'Voix')
        voices.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.voice = VoicePicker(tasks, self, form=voices)
        self.voice.hide()
        trans = page_form(self, 'Traduction')
        self.translate = QCheckBox('Traduire les sous-titres avant le doublage')
        self.translation_engine = combo([('Traduction locale · CTranslate2', 'ctranslate2'), ('Google · en ligne', 'google')], 'Moteur de traduction')
        self.translate_to = QLineEdit()
        self.translate_to.setAccessibleName('Langue cible de traduction')
        self.translate_to.setMaximumWidth(160)
        self.translate_from = QLineEdit()
        self.translate_from.setAccessibleName('Langue source de traduction')
        self.translate_from.setPlaceholderText('Automatique')
        self.translate_from.setMaximumWidth(160)
        trans.addRow(self.translate)
        trans.addRow('Moteur', self.translation_engine)
        trans.addRow('Langue cible (fr, en…)', self.translate_to)
        trans.addRow('Langue source', self.translate_from)
        advanced = page_form(self, 'Audio et temps')
        self.fields = {}
        for key, label, choices in FIELDS[7:]:
            if key == 'limit_duration_sec':
                continue  # La plage d’essai est gérée hors des réglages de production.
            if choices:
                widget = combo([(x.upper(), x) for x in choices], label)
            elif key in ('audio_bitrate', 'offset_ms', 'offset_video_ms', 'limit_duration_sec'):
                widget = QSpinBox()
                widget.setRange(-3600000 if key.startswith('offset') else 0, 3600000)
                if key == 'limit_duration_sec':
                    widget.setSpecialValueText('Vidéo entière')
                if key == 'audio_bitrate':
                    widget.setMinimum(8)
                    widget.setMaximum(1536)
            else:
                widget = QDoubleSpinBox()
                widget.setDecimals(1)
                widget.setRange(-100 if key == 'ducking_db' else 0.1 if key.endswith('rate_tts') else 0, 100)
                widget.setSingleStep(0.1)
            widget.setAccessibleName(label)
            widget.setMaximumWidth(260)
            self.fields[key] = widget
            if isinstance(widget, QAbstractSpinBox):
                widget.setLocale(QLocale.c())
                widget.setGroupSeparatorShown(False)
                widget.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
                widget.setStyleSheet('min-height: 30px; padding: 0 8px; border: 1px solid #858585; border-radius: 0;')
                row = QWidget()
                row.setMaximumWidth(260)
                layout = QHBoxLayout(row)
                layout.setContentsMargins(0, 0, 0, 0)
                layout.setSpacing(6)
                for text, action, name in (('+', widget.stepUp, 'Augmenter'), ('-', widget.stepDown, 'Diminuer')):
                    button = QPushButton(text)
                    button.setAutoDefault(False)
                    button.setAccessibleName(f'{name} : {label}')
                    button.setToolTip(f'{name} : {label}')
                    button.setAutoRepeat(True)
                    button.setStyleSheet('min-height: 30px; max-width: 30px; min-width: 30px; padding: 0;')
                    button.clicked.connect(action)
                    layout.addWidget(button)
                layout.addWidget(widget, 1)
                advanced.addRow(label.split(' ;')[0], row)
            else:
                advanced.addRow(label.split(' ;')[0], widget)
        for widget in (self.audio, self.sub, self.translation_engine, *self.fields.values()):
            signal = widget.currentIndexChanged if hasattr(widget, 'currentIndexChanged') else widget.valueChanged
            signal.connect(self.emit_change)
        self.voice.changed.connect(self.emit_change)
        self.translate.toggled.connect(self.translation_enabled)
        self.translate.toggled.connect(self.emit_change)
        self.translate_to.textChanged.connect(self.emit_change)
        self.translate_from.textChanged.connect(self.emit_change)

    def translation_enabled(self):
        for widget in (self.translation_engine, self.translate_to, self.translate_from):
            widget.setEnabled(self.translate.isChecked())

    def emit_change(self):
        if not self.loading:
            self.changed.emit()

    def load(self, settings, video):
        self.loading = True
        self.video = video
        self.base = adapt_settings(settings, video)
        for box, tracks, key in ((self.audio, video.audio, 'audio_index'), (self.sub, video.subtitles, 'sub')):
            box.clear()
            for track in tracks:
                box.addItem(track.label, track.value)
            choose(box, self.base.values[key])
            box.setToolTip(box.currentText())
        values = self.base.values
        self.translate.setChecked(self.base.translate)
        choose(self.translation_engine, values['translation_engine'])
        self.translate_to.setText(values['translate_to'])
        self.translate_from.setText(values['translate_from'])
        for key, widget in self.fields.items():
            if isinstance(widget, QComboBox):
                choose(widget, values[key])
            else:
                value = float(values[key] or 0)
                widget.setValue(int(value) if isinstance(widget, QSpinBox) else value)
        self.voice.set_value(values['tts_engine'], values['voice'], values['translate_to'])
        self.translation_enabled()
        self.loading = False

    def settings(self):
        result = deepcopy(self.base)
        if result is None:
            raise ValueError('Attendez la détection des pistes.')
        result.translate = self.translate.isChecked()
        result.values['limit_duration_sec'] = ''
        for key, box in (('audio_index', self.audio), ('sub', self.sub), ('translation_engine', self.translation_engine)):
            result.values[key] = box.currentData() or ''
        result.audio = next((t for t in self.video.audio if t.value == result.values['audio_index']), None)
        result.subtitle = next((t for t in self.video.subtitles if t.value == result.values['sub']), None)
        result.values['tts_engine'], result.values['voice'] = self.voice.value()
        result.values['translate_to'] = self.translate_to.text().strip()
        result.values['translate_from'] = self.translate_from.text().strip()
        for key, widget in self.fields.items():
            value = widget.currentData() if isinstance(widget, QComboBox) else widget.value()
            result.values[key] = '' if key == 'limit_duration_sec' and value == 0 else str(value)
        return result
