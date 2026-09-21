"""Test de chargement reel, dans un processus neuf apres installation."""
import sys


def main():
    try:
        import ctranslate2  # noqa: F401
    except (ImportError, OSError) as exc:
        print(f"[ERREUR] Impossible de charger CTranslate2 : {exc}", file=sys.stderr)
        if isinstance(exc, ModuleNotFoundError) and exc.name == "ctranslate2":
            print("[AIDE] CTranslate2 n'est pas installe. Relancez : python -m pip install -r requirements.txt", file=sys.stderr)
        elif sys.platform == "win32":
            print(
                "[AIDE] Une DLL peut etre absente ou incompatible. "
                "Installez/reparez Microsoft Visual C++ Redistributable x64 : "
                "https://aka.ms/vc14/vc_redist.x64.exe\n"
                "Puis relancez start_add_dub.bat (redemarrez Windows si demande). "
                "Si le probleme persiste, conservez l'erreur ci-dessus : "
                "Visual C++ n'est pas la seule cause possible.",
                file=sys.stderr,
            )
        return 1
    print('[OK] CTranslate2 charge correctement.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
