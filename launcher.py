# launcher.py
import sys, subprocess, json, hashlib, os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
VENV_DIR = PROJECT_ROOT / ".venv"              # ton venv
REQ_FILE = PROJECT_ROOT / "requirements.txt"
STAMP_FILE = PROJECT_ROOT / ".setup_done.json"
MAIN_SCRIPT = PROJECT_ROOT / "add_dub.py"  # <-- mets ici le nom du script à lancer

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def read_stamp():
    try:
        return json.loads(STAMP_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None

def write_stamp(data: dict):
    STAMP_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

def need_setup(force: bool) -> bool:
    if force:
        return True
    if not REQ_FILE.exists():
        # Pas de requirements => rien à installer
        return False
    if not STAMP_FILE.exists():
        return True
    try:
        stamp = read_stamp()
        if not stamp:
            return True
        req_hash = sha256_file(REQ_FILE)
        py_ver = "{}.{}.{}".format(*sys.version_info[:3])
        return not (stamp.get("req_hash") == req_hash and stamp.get("python") == py_ver)
    except Exception:
        return True

def pip_install():
    # Utilise le pip du Python courant (idéalement ton venv activé par le .bat)
    cmd = [
        sys.executable, "-m", "pip", "install",
        "--disable-pip-version-check", "--no-input",
        "-r", str(REQ_FILE)
    ]
    print("• Installation / mise à jour des dépendances…")
    subprocess.run(cmd, check=True)

def main():
    force = ("--force-setup" in sys.argv)
    # Optionnel : vérifier qu’on tourne dans le venv attendu
    if VENV_DIR.exists():
        expected_python = VENV_DIR / "Scripts" / "python.exe"
        if os.name == "nt" and Path(sys.executable).resolve() != expected_python.resolve():
            print("⚠️  Tu n’es pas dans le bon venv. Lance via start_add_dub.bat.")
            # On peut quand même tenter d’exécuter, mais on prévient.
    if need_setup(force):
        if not REQ_FILE.exists():
            print("⚠️  requirements.txt introuvable, on continue sans installation.")
        else:
            pip_install()
            stamp = {
                "req_hash": sha256_file(REQ_FILE),
                "python": "{}.{}.{}".format(*sys.version_info[:3]),
            }
            write_stamp(stamp)
            print("✓ Dépendances OK (tampon créé).")

    # Lancer l’outil
    print("→ Lancement de", MAIN_SCRIPT.name)
    # On forwarde les arguments (sans --force-setup)
    args = [a for a in sys.argv[1:] if a != "--force-setup"]
    subprocess.run([sys.executable, str(MAIN_SCRIPT), *args], check=True)

if __name__ == "__main__":
    main()
