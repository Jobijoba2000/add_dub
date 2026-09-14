"""Supervision Windows d'une commande batch, hors du moteur TTS."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

CHILD_ENV = 'ADD_DUB_BATCH_LIFECYCLE'


class ProcessJob:
    """Windows ferme tous les descendants lorsque le superviseur ferme ce job."""

    def __init__(self):
        class Limits(ctypes.Structure):
            _fields_ = [('process_time', ctypes.c_int64), ('job_time', ctypes.c_int64),
                        ('flags', wintypes.DWORD), ('min_ws', ctypes.c_size_t),
                        ('max_ws', ctypes.c_size_t), ('active', wintypes.DWORD),
                        ('affinity', ctypes.c_size_t), ('priority', wintypes.DWORD),
                        ('scheduling', wintypes.DWORD)]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [('basic', Limits), ('io', ctypes.c_uint64 * 6),
                        ('process_memory', ctypes.c_size_t), ('job_memory', ctypes.c_size_t),
                        ('peak_process_memory', ctypes.c_size_t), ('peak_job_memory', ctypes.c_size_t)]

        self.api = ctypes.WinDLL('kernel32', use_last_error=True)
        for name, args, result in [
            ('CreateJobObjectW', [ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
            ('SetInformationJobObject', [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD], wintypes.BOOL),
            ('AssignProcessToJobObject', [wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
            ('CloseHandle', [wintypes.HANDLE], wintypes.BOOL),
        ]:
            fn = getattr(self.api, name)
            fn.argtypes, fn.restype = args, result
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = ExtendedLimits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def assign(self, process):
        if not self.api.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


def run_child(batch_main, args, directory):
    directory = Path(directory)
    # Aucun worker ne démarre avant son rattachement au job Windows.
    deadline = time.monotonic() + 30
    while not (directory / 'ready').exists():
        if time.monotonic() >= deadline:
            raise RuntimeError('Le superviseur batch ne répond pas.')
        time.sleep(0.05)
    code = batch_main(args)
    # batch_main est revenu : mixage, nettoyage et manifeste GUI sont terminés.
    sys.stdout.flush()
    sys.stderr.flush()
    temporary = directory / 'complete.tmp'
    temporary.write_text(json.dumps({'code': code}), encoding='utf-8')
    temporary.replace(directory / 'complete.json')
    return code


def supervise(command, grace_seconds=2.0):
    with tempfile.TemporaryDirectory(prefix='add-dub-batch-') as directory:
        environment = os.environ.copy()
        environment[CHILD_ENV] = directory
        job = ProcessJob()
        process = None
        try:
            # Flux hérités : progression et erreurs restent visibles dans CMD/GUI.
            process = subprocess.Popen(command, env=environment)
            job.assign(process)
            Path(directory, 'ready').touch()
            completion = Path(directory, 'complete.json')
            while process.poll() is None and not completion.exists():
                time.sleep(0.05)
            if not completion.exists():
                # Un crash ne doit jamais être transformé en succès.
                return process.wait() or 1
            code = json.loads(completion.read_text(encoding='utf-8'))['code']
            try:
                exit_code = process.wait(timeout=grace_seconds)
                return exit_code if exit_code else code
            except subprocess.TimeoutExpired:
                print('[BATCH] Traitement terminé ; fermeture des processus restants.', flush=True)
                job.close()
                process.wait(timeout=10)
                return code
        finally:
            job.close()
            if process is not None and process.poll() is None:
                process.kill()
                process.wait(timeout=10)


def run(batch_main, args, argv):
    if os.name != 'nt':
        return batch_main(args)
    directory = os.environ.get(CHILD_ENV)
    if directory:
        return run_child(batch_main, args, directory)
    command = [sys.executable]
    if not getattr(sys, 'frozen', False):
        command += ['-m', 'add_dub']
    return supervise(command + list(argv))
