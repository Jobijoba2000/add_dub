"""Thème Qt sombre validé avec la Loupe Windows."""
from pathlib import Path
import sys
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QColor, QFont, QPalette, QPainter, QPen, QBrush, QPainterPath, QPixmap, QIcon
from PySide6.QtWidgets import QStyleFactory, QProxyStyle, QStyle


def icons8_icon(name):
    root = Path(sys._MEIPASS) if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1]
    asset_root = root / 'docs' / 'icons8'
    path = asset_root / f'{name}.png'
    if not path.is_file():
        path = asset_root / f'{name}.svg'
    if not path.is_file():
        return QIcon()
    return QIcon(str(path))


def playback_icon(stopped):
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor('#ffffff'))
    if stopped:
        painter.drawRoundedRect(12, 12, 40, 40, 3, 3)
    else:
        path = QPainterPath()
        path.moveTo(16, 8)
        path.lineTo(54, 32)
        path.lineTo(16, 56)
        path.closeSubpath()
        painter.drawPath(path)
    painter.end()
    icon = QIcon(pixmap)
    disabled = pixmap.copy()
    painter = QPainter(disabled)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(disabled.rect(), QColor('#909090'))
    painter.end()
    icon.addPixmap(disabled, QIcon.Mode.Disabled)
    return icon


def video_file_icon():
    """Pictogramme de pellicule lisible même sans association vidéo Windows."""
    icon = icons8_icon('video')
    if not icon.isNull():
        return icon
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor('#e5f1ff'))
    painter.drawRoundedRect(5, 9, 54, 46, 4, 4)
    painter.setBrush(QColor('#175782'))
    for x in (10, 24, 38, 50):
        for y in (13, 45):
            painter.drawRect(x, y, 5, 6)
    painter.drawRect(10, 23, 44, 18)
    painter.end()
    return QIcon(pixmap)


def settings_icon():
    icon = icons8_icon('settings')
    if not icon.isNull():
        return icon
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.translate(32, 32)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor('#d7e4f2'))
    for _ in range(8):
        painter.drawRoundedRect(-5, -28, 10, 14, 2, 2)
        painter.rotate(45)
    ring = QPainterPath()
    ring.addEllipse(-21, -21, 42, 42)
    ring.addEllipse(-10, -10, 20, 20)
    painter.drawPath(ring)
    painter.end()
    return QIcon(pixmap)


class WindowsCheckboxStyle(QProxyStyle):
    """Cases blanches à marquage noir, lisibles sur le thème sombre."""

    def drawPrimitive(self, element, option, painter, widget=None):
        if element == QStyle.PrimitiveElement.PE_IndicatorRadioButton:
            rect = option.rect.adjusted(1, 1, -1, -1)
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(QPen(QColor('#8f8f8f'), 1))
            painter.setBrush(QColor('#ffffff'))
            painter.drawEllipse(rect)
            if option.state & QStyle.StateFlag.State_On:
                inset = 3
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor('#050505'))
                painter.drawEllipse(rect.adjusted(inset, inset, -inset, -inset))
            painter.restore()
            return
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
                    inset = 3
                    inner = rect.adjusted(inset, inset, -inset, -inset)
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QBrush(QColor('#050505')))
                    painter.drawRect(inner)
                elif checked:
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                    painter.setPen(QPen(QColor('#050505'), 2))
                    path = QPainterPath()
                    path.moveTo(QPointF(rect.left() + rect.width() * .18, rect.top() + rect.height() * .52))
                    path.lineTo(QPointF(rect.left() + rect.width() * .43, rect.bottom() - rect.height() * .20))
                    path.lineTo(QPointF(rect.right() - rect.width() * .15, rect.top() + rect.height() * .22))
                    painter.drawPath(path)
                painter.restore()
                return
        super().drawPrimitive(element, option, painter, widget)

def apply_theme(app):
    app.setFont(QFont("Segoe UI", 10))
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
        QScrollBar:vertical {
            background: #151515; width: 12px; margin: 0; border: none;
        }
        QScrollBar:horizontal {
            background: #151515; height: 12px; margin: 0; border: none;
        }
        QScrollBar::handle:vertical {
            background: #707070; min-height: 36px; margin: 2px;
            border-radius: 4px;
        }
        QScrollBar::handle:horizontal {
            background: #707070; min-width: 36px; margin: 2px;
            border-radius: 4px;
        }
        QScrollBar::handle:hover { background: #a0a0a0; }
        QScrollBar::handle:pressed { background: #c0c0c0; }
        QScrollBar::add-line, QScrollBar::sub-line {
            width: 0; height: 0; border: none; background: transparent;
        }
        QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
        QAbstractScrollArea::corner { background: #151515; border: none; }
        QProgressBar {
            border: 1px solid #858585; border-radius: 4px;
            background-color: #191919; color: #ffffff;
            min-height: 26px; text-align: center; padding: 2px;
        }
        QProgressBar::chunk {
            background-color: #176b35; border-radius: 2px;
        }
        QLabel, QCheckBox, QRadioButton { background-color: transparent; }
        QLabel#heading { font-size: 28px; font-weight: bold; }
        QGroupBox { background-color: #171717; border: none; border-radius: 8px;
                    margin-top: 12px; padding: 20px 14px 14px; }
        QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 6px; }
        QGroupBox#outputPanel { background-color: transparent; border: none;
                                border-radius: 0; margin-top: 0; padding: 0; }
        QGroupBox#outputPanel::title { left: 0; padding: 0; }
        QPushButton, QComboBox, QLineEdit, QTextEdit, QTreeWidget {
            background-color: #0d0d0d; border: 1px solid #858585;
            border-radius: 5px; padding: 7px 10px;
        }
        QComboBox, QLineEdit { min-height: 24px; }
        QPushButton { background-color: #242424; min-height: 30px; padding: 8px 20px; }
        QPushButton#primary { background-color: #005fb8; border-color: #69a9e5; font-weight: bold; }
        QPushButton:hover { background-color: #303030; border-color: #b8b8b8; }
        QPushButton#primary:hover { background-color: #0872cf; }
        QTabBar#queueTabs::tab { background: #191919; color: #eeeeee;
            border: 1px solid #858585; border-bottom: none;
            padding: 8px 16px; margin-right: 8px; }
        QTabBar#queueTabs::tab:selected { background: #242424;
            color: #ffffff; font-weight: bold; }
        QTabBar#queueTabs::tab:hover { background: #404040; }
        QTabWidget#settingsTabs::pane { border: 1px solid #858585; border-top: none; }
        QTabWidget#settingsTabs QScrollArea { border: none; border-radius: 0; }
        QToolButton { border: 1px solid #858585; border-radius: 5px; padding: 8px; background: #242424; }
        QToolButton:hover { background: #404040; border-color: #d0d0d0; }
        QToolButton:pressed { background: #505050; }
        QToolButton#openSources::menu-indicator {
            subcontrol-origin: padding; subcontrol-position: bottom right;
            right: 7px; bottom: 7px;
        }
        QMenu { background-color: #242424; border: 1px solid #999999; padding: 5px; }
        QMenu::item { padding: 10px 28px; border: 1px solid transparent; }
        QMenu::icon { padding-left: 10px; padding-right: 6px; }
        QMenu::item:selected { background-color: #005fb8; border-color: #81bfff; }
        QMenu::item:disabled { color: #b0b0b0; }
        QMenu::separator { height: 1px; background: #858585; margin: 5px; }
        QComboBox:hover { background-color: #303030; border-color: #d0d0d0; }
        QToolButton#playback { background-color: #176b35; border-color: #75ba8a; font-weight: bold; }
        QToolButton#playback:hover { background-color: #207d42; }
        QToolButton#playback[processing="true"] { background-color: #a62429; border-color: #e88d90; }
        QToolButton#playback[processing="true"]:hover { background-color: #bd3036; }
        QToolButton:disabled { background-color: #383838; border-color: #858585; color: #dedede; }
        QToolButton#playback:disabled { background-color: #242424; border-color: #606060; color: #a0a0a0; font-weight: normal; }
        QPushButton:focus, QComboBox:focus, QLineEdit:focus, QTextEdit:focus, QTreeWidget:focus { border: 1px solid #ffdf00; }
        QCheckBox:focus { outline: 2px solid #ffdf00; }
        QRadioButton:focus { outline: none; }
        QRadioButton:focus { color: #ffdf00; }
        QRadioButton::indicator, QCheckBox::indicator { width: 16px; height: 16px; }
        QRadioButton { spacing: 12px; padding-top: 3px; padding-bottom: 3px; }
        QHeaderView::section { background-color: #242424; color: #f5f5f5; padding: 7px; border: none; border-bottom: 1px solid #858585; }
        QTreeWidget::item { padding: 3px 0; }
        QTreeWidget::item:hover:!selected { background-color: #303030; }
        QTreeWidget::indicator { width: 16px; height: 16px; }
        QTreeWidget::item:selected { background-color: #005fb8; color: #ffffff; }
        QTreeWidget#queueList { padding: 0; border-radius: 0; border-top: none; }
        QTreeWidget#queueList::item { padding: 0px 4px; margin: 0;
            border: none; border-top: 1px solid transparent; border-bottom: 1px solid transparent; }
        QTreeWidget#queueList::item:hover:!selected { background-color: #303030;
            border-top: 1px solid #505050; border-bottom: 1px solid #505050; }
        QTreeWidget#queueList::item:selected { background-color: #005fb8;
            border-top: 1px solid transparent; border-bottom: 1px solid transparent; }
        QTreeWidget#queueList QHeaderView::section { padding: 5px 7px;
            border-right: 1px solid #858585; }
    ''')
