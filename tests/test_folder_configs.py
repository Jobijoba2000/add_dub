import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


class FolderConfigurationTests(unittest.TestCase):
    def test_defaults_nested_priority_navigation_and_removal(self):
        from PySide6.QtWidgets import QApplication
        from add_dub.cli.args import parse_args
        from add_dub.gui.model import Job, Settings, Video, Track
        from add_dub.gui.dialog import ConfigureDialog, COMMON
        from add_dub.gui.batch import export_commands
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'Films'
            child = root / 'Suite'
            child.mkdir(parents=True)
            videos = [Video(str(p), str(root), [Track('0', 'Audio')], [Track('srt', 'SRT')])
                      for p in [root / 'a.mkv', child / 'b.mkv']]
            for video in videos:
                Path(video.path).touch()
            settings = Settings.from_args(parse_args(['--gui', '--tts-engine', 'gtts', '--voice', 'fr'])[0])
            dialog = ConfigureDialog(Job([str(root)], settings, directory, videos=videos), Mock())
            try:
                dialog.show()
                app.processEvents()
                dialog.build_tree()
                dialog.open_config(COMMON)
                defaults = dialog.config_defaults.values['ducking_db']
                dialog.editor.fields['ducking_db'].setValue(-19)
                dialog.create_folder_config(str(root))
                app.processEvents()
                self.assertTrue(dialog.config_buttons[str(root)].isChecked())
                self.assertFalse(dialog.config_buttons[COMMON].isChecked())
                from PySide6.QtCore import QPoint, Qt
                button_top = dialog.config_buttons[COMMON].mapTo(dialog, QPoint()).y()
                tree_top = dialog.tree.mapTo(dialog, QPoint()).y()
                self.assertEqual(button_top, tree_top)
                self.assertTrue(dialog.file_items[videos[1].path].data(0, Qt.ItemDataRole.UserRole + 8))
                self.assertEqual(dialog.job.folder_configs[str(root)].values['ducking_db'], defaults)
                self.assertIsNotNone(dialog.tree.itemWidget(dialog.folder_items[str(root)], 2))
                dialog.editor.fields['ducking_db'].setValue(-10)
                dialog.create_folder_config(str(child))
                self.assertEqual(dialog.job.folder_configs[str(child)].values['ducking_db'], defaults)
                dialog.editor.fields['ducking_db'].setValue(-6)
                self.assertEqual(float(dialog.job.settings_for(videos[0]).values['ducking_db']), -10)
                self.assertEqual(float(dialog.job.settings_for(videos[1]).values['ducking_db']), -6)
                # Le catalogue de voix est asynchrone et simulé dans ce test.
                for config in dialog.job.folder_configs.values():
                    config.values['voice'] = 'fr'
                self.assertEqual(len(export_commands(dialog.job)), 2)
                dialog.select_item(dialog.file_items[videos[1].path], None)
                self.assertEqual(dialog.current_path, str(child))
                self.assertFalse(dialog.job.overrides)
                dialog.remove_folder_config(str(child))
                self.assertEqual(dialog.current_path, str(root))
                self.assertEqual(float(dialog.job.settings_for(videos[1]).values['ducking_db']), -10)
                dialog.remove_folder_config(str(root))
                self.assertEqual(dialog.current_path, COMMON)
                self.assertTrue(dialog.config_buttons[COMMON].isChecked())
                self.assertEqual(dialog.file_items[videos[1].path].background(0).style(), Qt.BrushStyle.NoBrush)
                self.assertEqual(float(dialog.job.settings_for(videos[1]).values['ducking_db']), -19)
            finally:
                dialog.close()
                dialog.deleteLater()
