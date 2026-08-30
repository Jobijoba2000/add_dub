# add_dub/gui/app.py
from __future__ import annotations

import os
import sys
import time
import subprocess
import webbrowser
from typing import Optional

import add_dub.io.fs as io_fs
from add_dub.gui.server import start_server, GLOBAL_STATE
from add_dub.i18n import init_language


def find_edge_executable() -> Optional[str]:
    """
    Recherche le binaire msedge.exe dans les répertoires d'installation Windows standards.
    """
    candidates = [
        os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), r"Microsoft\Edge\Application\msedge.exe"),
        os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), r"Microsoft\Edge\Application\msedge.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Microsoft\Edge\Application\msedge.exe"),
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


def main():
    init_language()
    io_fs.ensure_base_dirs()

    # Démarrage du serveur local
    server, port = start_server(0)
    url = f"http://127.0.0.1:{port}"

    edge_bin = find_edge_executable()

    profile_dir = os.path.join(io_fs.TMP_DIR, "edge_profile")
    os.makedirs(profile_dir, exist_ok=True)

    edge_process: Optional[subprocess.Popen] = None
    if edge_bin:
        # Lancement en mode application autonome avec profil isolé
        cmd = [
            edge_bin,
            f"--app={url}",
            f"--user-data-dir={profile_dir}",
            "--start-maximized",
            "--disable-features=Translate",
            "--no-first-run",
            "--no-default-browser-check",
        ]
        try:
            edge_process = subprocess.Popen(cmd)
        except Exception:
            webbrowser.open(url)
    else:
        webbrowser.open(url)

    start_time = time.time()
    try:
        while True:
            time.sleep(0.5)

            # Si le processus Edge est toujours actif, continuer
            if edge_process and edge_process.poll() is None:
                continue

            now = time.time()
            # Délai de grâce initial de 12 secondes pour permettre l'ouverture et le premier chargement
            if now - start_time < 12.0:
                continue

            # Arrêt si signal explicite ou absence de heartbeat depuis plus de 4 secondes
            if GLOBAL_STATE.should_exit or (now - GLOBAL_STATE.last_heartbeat > 4.0):
                break

    except KeyboardInterrupt:
        pass
    finally:
        try:
            server.shutdown()
            server.server_close()
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
