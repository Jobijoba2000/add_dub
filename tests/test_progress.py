import unittest
from add_dub.progress import VideoProgress, aggregate, remaining_seconds


class ProgressTests(unittest.TestCase):
    def test_restart_after_clearing_old_jobs_ignores_empty_batches(self):
        from unittest.mock import patch, Mock
        from PySide6.QtWidgets import QApplication
        from add_dub.gui.application import Application
        from add_dub.gui.model import Job, Settings, Video, Track
        from add_dub.cli.args import parse_args
        app = QApplication.instance() or QApplication([])
        with patch('add_dub.gui.application.fs.ensure_base_dirs'):
            window = Application(parse_args(['--gui'])[0])
        old_video = Video('old.mkv', audio=[Track('0', 'Audio')], subtitles=[Track('srt', 'SRT')])
        old_job = Job([], Settings({}), 'output', videos=[old_video])
        try:
            window.jobs = [old_job]
            window.refresh()
            window.remove_entries('all')
            old_job.commands = Mock(side_effect=AssertionError('Ancien lot vide validé'))
            video = Video('new.mkv', audio=[Track('0', 'Audio')], subtitles=[Track('srt', 'SRT')])
            new_job = Job([], Settings({}), 'output', videos=[video])
            new_job.commands = Mock(return_value=[(video, ['python', '--batch'])])
            window.jobs.append(new_job)
            with patch('add_dub.gui.application.partition_existing', side_effect=lambda pending: (pending, [])), \
                 patch.object(window, 'next_file'), \
                 patch('add_dub.gui.application.QMessageBox.warning') as warning:
                window.start()
            warning.assert_not_called()
            old_job.commands.assert_not_called()
            new_job.commands.assert_called_once()
            self.assertTrue(window.running)
            self.assertEqual(window.pending, [(1, video, ['python', '--batch'])])
        finally:
            window.running = False
            window.clock_timer.stop()
            window.close()
            window.deleteLater()

    def test_queue_menu_paths_removal_and_immediate_transfer(self):
        from unittest.mock import patch
        from PySide6.QtWidgets import QApplication
        from add_dub.gui.application import Application
        from add_dub.gui.model import Job, Settings, Video, Track
        from add_dub.cli.args import parse_args
        app = QApplication.instance() or QApplication([])
        with patch('add_dub.gui.application.fs.ensure_base_dirs'):
            window = Application(parse_args(['--gui'])[0])
        videos = [Video(f'C:/source/episode{i}.mkv', audio=[Track('0', 'Audio')],
                        subtitles=[Track('srt', 'Sous-titres')]) for i in range(3)]
        job = Job([], Settings({}), 'C:/destination/output', videos=videos)
        window.jobs = [job]
        try:
            window.refresh()
            key = (0, videos[0].path)
            item = window.rows[key]
            self.assertEqual(item.text(0), 'episode0.mkv')
            self.assertEqual(item.text(1), 'output\\')
            self.assertEqual(item.toolTip(0), videos[0].path)
            menu = window.make_queue_menu(key)
            menu.actions()[0].trigger()
            self.assertEqual(item.text(0), videos[0].path)
            self.assertEqual(item.text(1), job.output + '\\')
            job.completed.add(videos[0].path)
            window.running = True
            window.file_finished = False
            window.active_key = (0, videos[1].path)
            window.refresh()
            self.assertIs(window.queue.topLevelItem(0), window.rows[window.active_key])
            self.assertEqual(item.text(2), 'Terminé')
            self.assertIs(item.treeWidget(), window.finished_queue)
            window.remove_entries('all')
            self.assertEqual(len(window.rows), 3)  # Liste verrouillée pendant le traitement.
            window.running = False
            window.remove_entries('completed')
            self.assertEqual(len(window.rows), 2)
            window.remove_entries((0, videos[1].path))
            self.assertEqual(len(window.rows), 1)
            window.remove_entries('all')
            self.assertEqual(len(window.rows), 0)
            self.assertFalse(window.start_button.isEnabled())
            menu.deleteLater()
        finally:
            window.running = False
            window.close()
            window.deleteLater()

    def test_real_child_process_progress_and_completion(self):
        import sys
        import time
        from types import SimpleNamespace
        from unittest.mock import patch
        from PySide6.QtWidgets import QApplication
        from add_dub.gui.application import Application
        from add_dub.cli.args import parse_args
        app = QApplication.instance() or QApplication([])
        with patch('add_dub.gui.application.fs.ensure_base_dirs'):
            window = Application(parse_args(['--gui'])[0])
        video = SimpleNamespace(path='simulation.mkv')
        script = "from add_dub.progress import stage, emit; stage('audio'); emit('progress',value=50); stage('mux'); emit('progress',value=100)"
        window.jobs = [SimpleNamespace(selected=[video], status='En attente', completed=set(),
                                       output_for=lambda v: 'output',
                                       commands=lambda: [(video, [sys.executable, '-c', script])])]
        try:
            window.start()
            deadline = time.monotonic() + 10
            while window.running and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(.01)
            self.assertFalse(window.running)
            self.assertEqual(window.jobs[0].completed, {video.path})
            self.assertEqual(window.progress.value(), 1000)
            self.assertEqual(window.finished_queue.topLevelItem(0).text(2), 'Terminé')
            self.assertEqual(window.queue.topLevelItemCount(), 0)
            self.assertFalse(window.start_button.isEnabled())
            self.assertNotIn('@@ADD_DUB_PROGRESS@@', '\n'.join(window.log_lines))
        finally:
            window.process.kill()
            window.process.waitForFinished(1000)
            window.running = False
            window.close()
            window.deleteLater()

    def test_cached_translation_is_removed(self):
        progress = VideoProgress()
        progress.update({'event': 'plan', 'translation': True})
        progress.update({'event': 'stage', 'name': 'translation'})
        progress.update({'event': 'skip', 'name': 'translation'})
        progress.update({'event': 'stage', 'name': 'audio'})
        self.assertNotIn('translation', progress.weights)
        self.assertEqual(progress.percent, 0)

    def test_smooth_wheel_uses_animation(self):
        from unittest.mock import Mock
        from PySide6.QtCore import QPoint
        from PySide6.QtWidgets import QApplication, QTreeWidgetItem
        from add_dub.gui.widgets import SmoothTreeWidget
        app = QApplication.instance() or QApplication([])
        tree = SmoothTreeWidget()
        tree.resize(300, 200)
        for index in range(100):
            QTreeWidgetItem(tree, [str(index)])
        tree.show()
        app.processEvents()
        event = Mock()
        event.modifiers.return_value = 0
        event.angleDelta.return_value = QPoint(0, -120)
        event.pixelDelta.return_value = QPoint(0, 0)
        tree.wheelEvent(event)
        self.assertGreater(tree._scroll.endValue(), 0)
        tree._scroll.setCurrentTime(220)
        self.assertGreater(tree.verticalScrollBar().value(), 0)
        tree.close()
        tree.deleteLater()

    def test_basic_weights_and_monotonic_progress(self):
        progress = VideoProgress()
        progress.update({'event': 'plan', 'subtitles': True})
        progress.update({'event': 'stage', 'name': 'subtitles'})
        progress.update({'event': 'stage', 'name': 'audio'})
        self.assertEqual(progress.percent, 1)
        progress.update({'event': 'progress', 'value': 100})
        self.assertEqual(progress.percent, 20)
        progress.update({'event': 'stage', 'name': 'tts'})
        progress.update({'event': 'progress', 'value': 50})
        self.assertEqual(progress.percent, 45)
        progress.update({'event': 'progress', 'value': 20})
        self.assertEqual(progress.percent, 45)
        progress.update({'event': 'stage', 'name': 'ducking'})
        self.assertEqual(progress.percent, 70)
        progress.update({'event': 'stage', 'name': 'mux'})
        self.assertEqual(progress.percent, 80)
        progress.update({'event': 'progress', 'value': 100})
        self.assertLess(progress.percent, 100)

    def test_optional_stages_are_normalized(self):
        progress = VideoProgress()
        self.assertNotIn('subtitles', progress.weights)
        self.assertNotIn('translation', progress.weights)
        progress.update({'event': 'plan', 'subtitles': True, 'translation': True})
        progress.update({'event': 'stage', 'name': 'subtitles'})
        progress.update({'event': 'stage', 'name': 'ocr'})
        self.assertEqual(sum(progress.weights.values()), 160)
        progress.update({'event': 'stage', 'name': 'translation'})
        self.assertAlmostEqual(progress.percent, 31 / 160 * 100)

    def test_total_and_eta(self):
        self.assertEqual(aggregate(0, 100, 50), .5)
        self.assertEqual(aggregate(1, 100, 50), 1.5)
        self.assertEqual(aggregate(100, 100), 100)
        self.assertEqual(aggregate(0, 0), 0)
        self.assertIsNone(remaining_seconds([], 99, 0))
        self.assertEqual(remaining_seconds([20], 99, 0), 1980)
        self.assertEqual(remaining_seconds([20, 40], 98, 50), 2925)

    def test_protocol_fragmentation_and_queue_rows(self):
        import json
        from types import SimpleNamespace
        from unittest.mock import patch
        from PySide6.QtWidgets import QApplication
        from add_dub.gui.application import Application
        from add_dub.cli.args import parse_args
        from add_dub.progress import PREFIX
        app = QApplication.instance() or QApplication([])
        with patch('add_dub.gui.application.fs.ensure_base_dirs'):
            window = Application(parse_args(['--gui'])[0])
        try:
            videos = [SimpleNamespace(path=f'episode{i}.mkv') for i in range(2)]
            window.jobs = [SimpleNamespace(selected=videos, status='En attente', completed=set(),
                                           output_for=lambda v: 'output/saison')]
            window.refresh()
            self.assertEqual(window.queue.topLevelItemCount(), 2)
            self.assertEqual(window.queue.columnCount(), 3)
            window.queue.setColumnWidth(0, 510)
            self.assertEqual(window.finished_queue.columnWidth(0), 510)
            original_rows = dict(window.rows)
            window.pending = [(0, v, []) for v in videos]
            window.running = True
            window.active_key = (0, videos[0].path)
            window.file_finished = False
            window.output_buffer = ''
            window.refresh()
            line = PREFIX + json.dumps({'event': 'stage', 'name': 'tts'}) + '\n'
            window.consume_output(line[:9])
            self.assertEqual(window.video_progress.label, 'Préparation')
            window.consume_output(line[9:])
            window.consume_output(PREFIX + json.dumps({'event': 'progress', 'value': 50}) + '\n')
            self.assertIn('Génération vocale', window.active_bar.format())
            self.assertGreater(window.progress.value(), 0)
            self.assertNotIn(PREFIX, '\n'.join(window.log_lines))
            window.consume_output('journal sans saut de ligne', final=True)
            self.assertIn('journal sans saut de ligne', '\n'.join(window.log_lines))
            window.jobs[0].completed.add(videos[0].path)
            window.active_key = (0, videos[1].path)
            window.refresh()
            for key, item in original_rows.items():
                self.assertIs(window.rows[key], item)
            self.assertEqual(window.queue.topLevelItemCount(), 1)
            self.assertEqual(window.finished_queue.topLevelItemCount(), 1)
            self.assertEqual(window.queue.topLevelItem(0).text(0), videos[1].path)
            self.assertEqual(window.finished_queue.topLevelItem(0).text(0), videos[0].path)
            self.assertEqual(window.queue.columnWidth(0), 510)
            for key, item in original_rows.items():
                self.assertIs(window.rows[key], item)
        finally:
            window.running = False
            window.close()
            window.deleteLater()


if __name__ == '__main__':
    unittest.main()
