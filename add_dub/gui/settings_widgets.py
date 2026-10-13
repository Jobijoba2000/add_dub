"""Contrôles de paramètres avec validation explicite et interrupteur animé."""
from add_dub.gui.translations import ui
import math
import re
from PySide6.QtCore import Qt, Property, QPropertyAnimation, QEasingCurve, Signal, QSize, QRectF
from PySide6.QtGui import QPainter, QColor, QPen
from PySide6.QtWidgets import QCheckBox, QWidget, QVBoxLayout, QLineEdit, QLabel


class AnimatedToggle(QCheckBox):
    def __init__(self, text='', parent=None):
        super().__init__(text, parent)
        self._position = 0.0
        self.animation = QPropertyAnimation(self, b'position', self)
        self.animation.setDuration(180)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(34)
        self.toggled.connect(self._animate)

    def _animate(self, checked):
        self.animation.stop()
        if not self.isVisible():
            self.position = float(checked)
            return
        self.animation.setStartValue(self._position)
        self.animation.setEndValue(float(checked))
        self.animation.start()

    def _get_position(self):
        return self._position

    def _set_position(self, value):
        self._position = value
        self.update()

    position = Property(float, _get_position, _set_position)

    def sizeHint(self):
        return QSize(62 + self.fontMetrics().horizontalAdvance(self.text()), 34)

    def hitButton(self, point):
        return self.rect().contains(point)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        y = (self.height() - 26) / 2
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor('#247bc1' if self.isChecked() else '#555555') if self.isEnabled() else QColor('#353535'))
        painter.drawRoundedRect(QRectF(2, y, 48, 26), 13, 13)
        painter.setBrush(QColor('#ffffff' if self.isEnabled() else '#858585'))
        painter.drawEllipse(QRectF(5 + 22 * self._position, y + 3, 20, 20))
        painter.setPen(QColor('#f5f5f5' if self.isEnabled() else '#858585'))
        painter.drawText(self.rect().adjusted(62, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter, self.text())
        if self.hasFocus():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor('#ffdf00'), 2))
            painter.drawRoundedRect(QRectF(0, y - 2, 52, 30), 15, 15)


class NumberField(QWidget):
    changed = Signal()
    validityChanged = Signal(bool)

    def __init__(self, minimum, maximum, *, integer=False, suffix='', parent=None):
        super().__init__(parent)
        self.minimum, self.maximum = minimum, maximum
        self.integer, self.suffix = integer, suffix
        self._external_error = ''
        self.editor = QLineEdit()
        self.editor.setMaximumWidth(240)
        self.editor.setStyleSheet('QLineEdit[invalid="true"] { border: 2px solid #f26c6c; }')
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self.editor)
        layout.addWidget(self.hint)
        self.editor.textChanged.connect(self._changed)
        self.editor.editingFinished.connect(self.normalize)
        self.setFocusProxy(self.editor)

    def setRange(self, minimum, maximum):
        self.minimum, self.maximum = minimum, maximum
        self._render()

    def setError(self, message=''):
        self._external_error = message
        self._render()

    def errorText(self):
        raw = self.text()
        if ',' in raw:
            return ui('Utilisez un point décimal, par exemple 1.5.')
        pattern = r'[+-]?\d+' if self.integer else r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)'
        if not re.fullmatch(pattern, raw):
            return ui('Entrez un nombre entier.') if self.integer else ui('Entrez un nombre avec un point décimal.')
        number = float(raw)
        if not math.isfinite(number) or not self.minimum <= number <= self.maximum:
            return f'{ui('Hors plage : ')}{self.minimum:g}{ui(' à ')}{self.maximum:g}{self.suffix}.'
        return self._external_error

    def isValid(self):
        return not self.errorText()

    def text(self):
        return self.editor.text().strip()

    def value(self):
        if not self.isValid():
            raise ValueError(self.errorText())
        return int(self.text()) if self.integer else float(self.text())

    def setValue(self, value):
        try:
            number = float(value)
            if math.isfinite(number) and self.minimum <= number <= self.maximum and (not self.integer or number.is_integer()):
                value = str(int(number)) if self.integer else f'{number:.1f}'
        except (ValueError, TypeError):
            pass
        self.editor.setText(str(value))

    def normalize(self):
        if self.isValid():
            self.setValue(self.value())

    def _changed(self):
        self._external_error = ''
        self._render()
        self.changed.emit()

    def _render(self):
        error = self.errorText()
        self.editor.setProperty('invalid', bool(error))
        self.editor.style().unpolish(self.editor)
        self.editor.style().polish(self.editor)
        fmt = '.0f' if self.integer else '.1f'
        bounds = f'{format(self.minimum, fmt)}{ui(' à ')}{format(self.maximum, fmt)}{self.suffix}'
        self.hint.setText(('! ' + error) if error else bounds)
        self.hint.setStyleSheet('color: #ff8b8b;' if error and self.isEnabled() else 'color: #999999;')
        self.editor.setAccessibleDescription(error or bounds)
        self.validityChanged.emit(not error)
