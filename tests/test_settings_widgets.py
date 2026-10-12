import os
import unittest
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import Qt, QLocale
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from add_dub.gui.settings_widgets import AnimatedToggle, NumberField


class SettingsWidgetsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_numeric_format_and_out_of_range_input_are_not_silently_clipped(self):
        old_locale = QLocale()
        QLocale.setDefault(QLocale('fr_FR'))
        field = NumberField(0, 10)
        try:
            field.setValue(1)
            self.assertEqual(field.text(), '1.0')
            field.editor.setText('1,5')
            self.assertFalse(field.isValid())
            field.setValue(20)
            self.assertEqual(field.text(), '20')
            self.assertFalse(field.isValid())
            self.assertTrue(field.editor.property('invalid'))
            field.editor.setText('1.5')
            self.assertEqual(field.value(), 1.5)
        finally:
            QLocale.setDefault(old_locale)
            field.deleteLater()

    def test_toggle_works_with_keyboard_and_animates(self):
        toggle = AnimatedToggle('Traduire')
        toggle.show()
        toggle.setFocus()
        QTest.keyClick(toggle, Qt.Key.Key_Space)
        self.assertTrue(toggle.isChecked())
        toggle.animation.setCurrentTime(90)
        self.assertGreater(toggle.position, 0)
        self.assertLess(toggle.position, 1)
        toggle.animation.setCurrentTime(180)
        self.assertEqual(toggle.position, 1)
        toggle.setEnabled(False)
        QTest.keyClick(toggle, Qt.Key.Key_Space)
        self.assertTrue(toggle.isChecked())
        toggle.close()
        toggle.deleteLater()
