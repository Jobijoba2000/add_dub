"""Taller Windows caption, with Qt controls and native move/resize actions.

Based on Microsoft's Custom Window Frame Using DWM example. No global Windows
metrics are changed. Other platforms retain their usual Qt window frame.
"""
import ctypes
import sys
from ctypes import wintypes

from PySide6.QtCore import Qt, QPoint, QEvent, QSize
from PySide6.QtGui import QIcon, QPixmap, QPainter, QPen, QColor
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMainWindow, QWidget, QToolButton, QStyle


class CaptionWindow(QMainWindow):
    caption_height = 40  # Logical pixels; Windows DPI scaling applies.

    def install_caption(self):
        self._caption_enabled = sys.platform == 'win32' and QApplication.platformName() == 'windows'
        if not self._caption_enabled:
            return
        self._user32 = ctypes.WinDLL('user32', use_last_error=True)
        self._dwm = ctypes.WinDLL('dwmapi')
        self._user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        self._user32.DefWindowProcW.restype = ctypes.c_ssize_t
        self._user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        self._user32.IsZoomed.argtypes = [wintypes.HWND]
        self._user32.GetDpiForWindow.argtypes = [wintypes.HWND]
        self._user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
        self._dwm.DwmDefWindowProc.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM, ctypes.POINTER(ctypes.c_ssize_t)]
        self._dwm.DwmExtendFrameIntoClientArea.argtypes = [wintypes.HWND, ctypes.c_void_p]
        self.caption = QWidget(self)
        self.caption.setFixedHeight(self.caption_height)
        self.caption.setStyleSheet('background-color: #202020; color: #f5f5f5;')
        row = QHBoxLayout(self.caption)
        # Reserve the native min/max/close area, including high-DPI scaling.
        row.setContentsMargins(12, 0, 0, 0)
        row.setSpacing(10)
        icon = QLabel()
        icon.setPixmap(self.windowIcon().pixmap(QSize(24, 24), self.devicePixelRatioF()))
        row.addWidget(icon)
        title = QLabel(self.windowTitle())
        self.windowTitleChanged.connect(title.setText)
        row.addWidget(title, 1)
        self.caption_buttons = QWidget()
        buttons = QHBoxLayout(self.caption_buttons)
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(0)
        for name, standard, action in (
            ('Réduire', QStyle.StandardPixmap.SP_TitleBarMinButton, self.showMinimized),
            ('Agrandir', QStyle.StandardPixmap.SP_TitleBarMaxButton, self.toggle_maximized),
            ('Fermer', QStyle.StandardPixmap.SP_TitleBarCloseButton, self.close),
        ):
            button = QToolButton()
            button.setAccessibleName(name)
            button.setToolTip(name)
            button.setFixedSize(46, self.caption_height)
            button.setIcon(self.caption_icon(standard))
            button.setStyleSheet('QToolButton {border: none; border-radius: 0; padding: 0; background: #202020;} '
                                'QToolButton:hover {background: ' + ('#c42b1c' if name == 'Fermer' else '#404040') + ';}')
            button.clicked.connect(action)
            buttons.addWidget(button)
            if name == 'Agrandir':
                self.caption_maximize = button
        row.addWidget(self.caption_buttons)
        self.setMenuWidget(self.caption)
        hwnd = int(self.winId())
        self._extend_caption(hwnd)
        self._user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x0037)

    def _extend_caption(self, hwnd):
        scale = self._user32.GetDpiForWindow(hwnd) / 96
        margins = (ctypes.c_int * 4)(0, 0, round(self.caption_height * scale), 0)
        self._dwm.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins))

    def toggle_maximized(self):
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def caption_icon(self, standard):
        # Draw at the display's pixel density instead of using theme glyphs,
        # which can be nearly black with the Windows11 Qt style.
        ratio = self.devicePixelRatioF()
        pixmap = QPixmap(round(16 * ratio), round(16 * ratio))
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setPen(QPen(QColor('#eeeeee'), 1))
        if standard == QStyle.StandardPixmap.SP_TitleBarMinButton:
            painter.drawLine(3, 8, 13, 8)
        elif standard == QStyle.StandardPixmap.SP_TitleBarCloseButton:
            painter.drawLine(3, 3, 13, 13)
            painter.drawLine(3, 13, 13, 3)
        elif standard == QStyle.StandardPixmap.SP_TitleBarNormalButton:
            painter.drawRect(5, 3, 8, 8)
            painter.fillRect(3, 5, 8, 8, QColor('#202020'))
            painter.drawRect(3, 5, 8, 8)
        else:
            painter.drawRect(3, 3, 10, 10)
        painter.end()
        return QIcon(pixmap)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and hasattr(self, 'caption_maximize'):
            restored = self.isMaximized()
            name = 'Restaurer' if restored else 'Agrandir'
            self.caption_maximize.setToolTip(name)
            self.caption_maximize.setAccessibleName(name)
            standard = QStyle.StandardPixmap.SP_TitleBarNormalButton if restored else QStyle.StandardPixmap.SP_TitleBarMaxButton
            self.caption_maximize.setIcon(self.caption_icon(standard))

    def nativeEvent(self, event_type, message):
        if not getattr(self, '_caption_enabled', False):
            return super().nativeEvent(event_type, message)
        msg = wintypes.MSG.from_address(int(message))
        if msg.message == 0x0083 and msg.wParam:  # WM_NCCALCSIZE
            # RECT[0] is the first field of NCCALCSIZE_PARAMS. Preserve Windows'
            # side/bottom borders and maximized work-area correction.
            rect = wintypes.RECT.from_address(msg.lParam)
            top = rect.top
            result = self._user32.DefWindowProcW(msg.hWnd, msg.message, msg.wParam, msg.lParam)
            if result:
                return True, result
            dpi = self._user32.GetDpiForWindow(msg.hWnd)
            border = (self._user32.GetSystemMetricsForDpi(33, dpi)
                      + self._user32.GetSystemMetricsForDpi(92, dpi))
            rect.top = top + (border if self._user32.IsZoomed(msg.hWnd) else 0)
            return True, 0
        if msg.message == 0x0084:  # WM_NCHITTEST
            if hasattr(self, 'caption_buttons'):
                # Native messages use physical desktop coordinates, Qt uses DIPs.
                point = wintypes.POINT(ctypes.c_short(msg.lParam & 0xffff).value,
                                       ctypes.c_short((msg.lParam >> 16) & 0xffff).value)
                self._user32.ScreenToClient.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
                self._user32.ScreenToClient(msg.hWnd, ctypes.byref(point))
                scale = self._user32.GetDpiForWindow(msg.hWnd) / 96
                local = self.caption_buttons.mapFrom(self, QPoint(round(point.x / scale), round(point.y / scale)))
                if self.caption_buttons.rect().contains(local):
                    return True, 1
            # Native side/bottom hit tests preserve resize cursors and behavior.
            hit = self._user32.DefWindowProcW(msg.hWnd, msg.message, msg.wParam, msg.lParam)
            if hit in (10, 11, 12, 13, 14, 15, 16, 17):
                return True, hit
            rect = wintypes.RECT()
            self._user32.GetWindowRect(msg.hWnd, ctypes.byref(rect))
            y = ctypes.c_short((msg.lParam >> 16) & 0xffff).value - rect.top
            scale = self._user32.GetDpiForWindow(msg.hWnd) / 96
            if not self._user32.IsZoomed(msg.hWnd) and y < round(6 * scale):
                return True, 12  # HTTOP
            if y < round(self.caption_height * scale):
                return True, 2  # HTCAPTION: native drag, double-click and menu.
            return True, 1  # HTCLIENT
        if msg.message in (0x0006, 0x02E0):  # activation / DPI change
            self._extend_caption(msg.hWnd)
        return super().nativeEvent(event_type, message)
