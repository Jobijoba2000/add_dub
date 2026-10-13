"""Portable launcher defaults and the console executable used by Qt workers."""
from pathlib import Path
import ctypes
from ctypes import wintypes
import subprocess
import sys

MODES = {'--interactive', '--batch', '--gui', '--player', '--player-generate'}


def launcher_arguments(argv):
    argv = list(argv)
    if not getattr(sys, 'frozen', False):
        return argv
    if any(argument.split('=', 1)[0] in MODES for argument in argv):
        return argv
    mode = {'add_dub': '--gui', 'add_dub_player': '--player'}.get(Path(sys.executable).stem.lower())
    return ([mode] + argv) if mode else argv


def worker_executable():
    if getattr(sys, 'frozen', False):
        console = Path(sys.executable).with_name('add_dub_console.exe')
        if console.is_file():
            return str(console)
    return sys.executable


def forward_console(argv):
    """Route explicit CLI requests from a windowed launcher to the console.

    PyInstaller windowed programs have no Python stdout/stderr. The console
    helper retains the OS pipes for --help and batch commands, and interactive
    requests open a usable console when launched from Explorer.
    """
    if not getattr(sys, 'frozen', False):
        return None
    if Path(sys.executable).stem.lower() not in ('add_dub', 'add_dub_player'):
        return None
    flags = {argument.split('=', 1)[0] for argument in argv}
    if not flags & {'--batch', '--interactive', '--player-generate', '--help', '-h', '--version'}:
        return None
    console = worker_executable()
    if console == sys.executable:
        return None
    if '--interactive' in flags:
        return subprocess.call([console, *argv])
    # A windowed PyInstaller bootloader has no Python stream objects even when
    # CMD or QProcess supplied OS pipes. Forward to those handles explicitly.
    process = subprocess.Popen([console, *argv], stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT,
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        for chunk in iter(lambda: process.stdout.read1(8192), b''):
            _write_stdout(chunk)
        return process.wait()
    finally:
        process.stdout.close()


def _write_stdout(data):
    if sys.stdout is not None:
        if hasattr(sys.stdout, 'buffer'):
            sys.stdout.buffer.write(data)
            sys.stdout.buffer.flush()
        else:
            sys.stdout.write(data.decode('utf-8', 'replace').replace('\r\n', '\n'))
            sys.stdout.flush()
        return
    if sys.platform != 'win32':
        return
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.GetStdHandle.argtypes = [wintypes.DWORD]
    api.GetStdHandle.restype = wintypes.HANDLE
    api.WriteFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                             ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    api.WriteFile.restype = wintypes.BOOL
    handle = api.GetStdHandle(wintypes.DWORD(-11))
    if handle and handle != ctypes.c_void_p(-1).value:
        written = wintypes.DWORD()
        api.WriteFile(handle, data, len(data), ctypes.byref(written), None)
