"""Thème Qt sombre validé avec la Loupe Windows."""
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QColor, QFont, QPalette, QPainter, QPen, QBrush, QPainterPath
from PySide6.QtWidgets import QStyleFactory, QProxyStyle, QStyle


class WindowsCheckboxStyle(QProxyStyle):
    """Cases blanches à marquage noir, lisibles sur le thème sombre."""

    def drawPrimitive(self, element, option, painter, widget=None):
        indicators = (QStyle.PrimitiveElement.PE_IndicatorItemViewItemCheck,
                      QStyle.PrimitiveElement.PE_IndicatorCheckBox)
        if element in indicators:
            rect = option.rect.adjusted(1, 1, -1, -1)
            if rect.width() >= 10 and rect.height() >= 10:
                state = option.state
                checked = bool(state & QStyle.StateFlag.State_On)
                partial = bool(state & QStyle.StateFlag.State_NoChange)
                painter.save()
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
                painter.setPen(QPen(QColor('#8f8f8f'), 1))
                painter.setBrush(QBrush(QColor('#ffffff')))
                painter.drawRect(rect)
                if partial:
                    # Le carré intermédiaire reste nettement visible à 125/150 %.
                    inner = rect.adjusted(rect.width() // 4, rect.height() // 4,
                                          -rect.width() // 4, -rect.height() // 4)
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QBrush(QColor('#050505')))
                    painter.drawRect(inner)
                elif checked:
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.setPen(QPen(QColor('#050505'), max(2, rect.width() // 7)))
                    path = QPainterPath()
                    path.moveTo(QPointF(rect.left() + rect.width() * .18, rect.top() + rect.height() * .52))
                    path.lineTo(QPointF(rect.left() + rect.width() * .43, rect.bottom() - rect.height() * .20))
                    path.lineTo(QPointF(rect.right() - rect.width() * .15, rect.top() + rect.height() * .22))
                    painter.drawPath(path)
                painter.restore()
                return
        super().drawPrimitive(element, option, painter, widget)

def apply_theme(app):
    app.setFont(QFont("Segoe UI", 11))
    styles = QStyleFactory.keys()
    base_name = next((style for style in styles if style.lower() == 'windows11'), 'Fusion')
    app.setStyle(WindowsCheckboxStyle(QStyleFactory.create(base_name)))
    app.styleHints().setColorScheme(Qt.ColorScheme.Dark)
    palette = QPalette()
    for role, color in ((QPalette.ColorRole.Window, '#090909'),
                        (QPalette.ColorRole.Base, '#0d0d0d'),
                        (QPalette.ColorRole.AlternateBase, '#191919'),
                        (QPalette.ColorRole.Button, '#242424')):
        palette.setColor(role, QColor(color))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        palette.setColor(role, QColor('#ffffff'))
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor('#ffffff'))
    palette.setColor(QPalette.ColorRole.Highlight, QColor('#005fb8'))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor('#ffffff'))
    app.setPalette(palette)
    app.setStyleSheet('''
        QWidget { color: #f5f5f5; background-color: #090909; }
        QScrollArea { border: none; }
        QLabel, QCheckBox, QRadioButton { background-color: transparent; }
        QLabel#heading { font-size: 28px; font-weight: bold; }
        QGroupBox { background-color: #171717; border: none; border-radius: 8px;
                    margin-top: 12px; padding: 20px 14px 14px; }
        QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 6px; }
        QPushButton, QComboBox, QLineEdit, QTextEdit, QTreeWidget {
            background-color: #0d0d0d; border: 1px solid #858585;
            border-radius: 5px; padding: 7px 10px;
        }
        QComboBox, QLineEdit { min-height: 24px; }
        QPushButton { background-color: #242424; min-height: 30px; padding: 8px 20px; }
        QPushButton#primary { background-color: #005fb8; border-color: #69a9e5; font-weight: bold; }
        QPushButton:hover { background-color: #303030; border-color: #b8b8b8; }
        QPushButton#primary:hover { background-color: #0872cf; }
        QPushButton:focus, QComboBox:focus, QLineEdit:focus, QTextEdit:focus, QTreeWidget:focus { border: 1px solid #ffdf00; }
        QCheckBox:focus, QRadioButton:focus { outline: 2px solid #ffdf00; }
        QRadioButton::indicator { width: 16px; height: 16px; border-radius: 9px;
                                   border: 1px solid #a0a0a0; background-color: #0d0d0d; }
        QRadioButton::indicator:checked { background-color: #75bfff; border-color: #c0dfff; }
        QHeaderView::section { background-color: #242424; color: #f5f5f5; padding: 7px; border: none; border-bottom: 1px solid #858585; }
        QTreeWidget::item { padding: 3px 0; }
        QTreeWidget::indicator { width: 20px; height: 20px; }
        QTreeWidget::item:selected { background-color: #005fb8; color: #ffffff; }
    ''')
