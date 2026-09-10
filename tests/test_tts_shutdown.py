import unittest
from unittest.mock import Mock

from add_dub.core.tts_generate import _shutdown_executor


class WorkerShutdownTests(unittest.TestCase):
    def test_finished_workers_are_not_terminated(self):
        worker = Mock()
        worker.is_alive.return_value = False
        executor = Mock(_processes={1: worker})
        _shutdown_executor(executor)
        executor.shutdown.assert_called_once_with(wait=False, cancel_futures=True)
        worker.join.assert_called_once()
        worker.terminate.assert_not_called()

    def test_stuck_worker_is_terminated_and_joined(self):
        worker = Mock(pid=42)
        worker.is_alive.side_effect = [True, False]
        executor = Mock(_processes={42: worker})
        _shutdown_executor(executor)
        worker.terminate.assert_called_once()
        worker.kill.assert_not_called()
        self.assertEqual(worker.join.call_count, 2)

    def test_unresponsive_worker_is_killed(self):
        worker = Mock(pid=42)
        worker.is_alive.return_value = True
        executor = Mock(_processes={42: worker})
        _shutdown_executor(executor)
        worker.kill.assert_called_once()


if __name__ == '__main__':
    unittest.main()
