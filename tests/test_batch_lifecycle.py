import os
import ctypes
from ctypes import wintypes
from pathlib import Path
import sys
import tempfile
import time
import unittest

from add_dub.cli.batch_lifecycle import supervise


@unittest.skipUnless(os.name == 'nt', 'Windows job objects')
class BatchLifecycleTests(unittest.TestCase):
    def test_finished_batch_with_blocked_thread_keeps_result(self):
        for code in (0, 7):
            with self.subTest(code=code):
                script = f'''
import os, threading, time
from add_dub.cli.batch_lifecycle import run_child, CHILD_ENV
def batch(args):
    threading.Thread(target=lambda: time.sleep(300)).start()
    return {code}
raise SystemExit(run_child(batch, None, os.environ[CHILD_ENV]))
'''
                started = time.monotonic()
                self.assertEqual(supervise([sys.executable, '-c', script], 0.2), code)
                self.assertLess(time.monotonic() - started, 10)

    def test_crash_without_completion_is_failure(self):
        self.assertEqual(supervise([sys.executable, '-c', 'raise SystemExit(9)'], 0.2), 9)

    def test_zero_exit_without_completion_is_not_success(self):
        self.assertNotEqual(supervise([sys.executable, '-c', 'pass'], 0.2), 0)

    def test_normal_completion_preserves_exit_status(self):
        script = '''
import os
from add_dub.cli.batch_lifecycle import run_child, CHILD_ENV
raise SystemExit(run_child(lambda args: 0, None, os.environ[CHILD_ENV]))
'''
        self.assertEqual(supervise([sys.executable, '-c', script], 0.2), 0)

    def test_descendant_is_closed_even_after_normal_parent_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            pid_file = Path(directory, 'child.pid')
            script = f'''
import os, subprocess, sys
from pathlib import Path
from add_dub.cli.batch_lifecycle import run_child, CHILD_ENV
def batch(args):
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(300)'])
    Path({str(pid_file)!r}).write_text(str(child.pid))
    return 0
raise SystemExit(run_child(batch, None, os.environ[CHILD_ENV]))
'''
            self.assertEqual(supervise([sys.executable, '-c', script], 0.2), 0)
            api = ctypes.WinDLL('kernel32', use_last_error=True)
            api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            api.OpenProcess.restype = wintypes.HANDLE
            api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            api.CloseHandle.argtypes = [wintypes.HANDLE]
            handle = api.OpenProcess(0x100000, False, int(pid_file.read_text()))
            if handle:
                try:
                    self.assertEqual(api.WaitForSingleObject(handle, 2000), 0)
                finally:
                    api.CloseHandle(handle)

    def test_grace_period_only_starts_after_batch_returns(self):
        script = '''
import os, time
from add_dub.cli.batch_lifecycle import run_child, CHILD_ENV
def batch(args):
    time.sleep(0.5)
    return 0
raise SystemExit(run_child(batch, None, os.environ[CHILD_ENV]))
'''
        started = time.monotonic()
        self.assertEqual(supervise([sys.executable, '-c', script], 0.1), 0)
        self.assertGreaterEqual(time.monotonic() - started, 0.5)
