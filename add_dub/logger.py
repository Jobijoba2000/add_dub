# add_dub/logger.py
# ------------------------------------------------------------
# Logger central du projet :
# - Lit la config console et fichier depuis options.conf via opts_loader
# - Écrit par défaut TOUT dans un fichier rotatif (3x~5Mo)
# - Affiche les logs en console avec timestamp + niveau
# - NE PASSE PAS les durées dans le fichier : @log_time imprime
#   uniquement "X.XXX s" en console (sans timestamp/LEVEL)
# ------------------------------------------------------------

import os
import sys
import time
import inspect
import hashlib
import logging
import threading
from functools import wraps
from logging.handlers import RotatingFileHandler
from add_dub.config.opts_loader import load_options, OptEntry



# ------------------------------------------------------------
# Lecture des réglages console depuis options.conf
#   [logging]
#   console_enable = true|false
#   console_level  = DEBUG|INFO|WARNING|ERROR|CRITICAL
# ------------------------------------------------------------
def _read_logging_config():
    opts = load_options()

    def _val(key, default):
        v = opts.get(key)
        return v.value if isinstance(v, OptEntry) else default

    return {
        "console_enable": bool(_val("logging.console_enable", True)),
        "console_level": str(_val("logging.console_level", "DEBUG")).upper(),
        "file_enable": bool(_val("logging.file_enable", True)),
        "file_level": str(_val("logging.file_level", "DEBUG")).upper(),
        "file_name": str(_val("logging.file_name", "add_dub.log")),
        "dir": str(_val("logging.dir", "logs")),
    }


def _read_console_config():
    config = _read_logging_config()
    return config["console_enable"], config["console_level"]


# ------------------------------------------------------------
# Logger central "add_dub"
# ------------------------------------------------------------
logger = logging.getLogger("add_dub")
logger.setLevel(logging.DEBUG)  # on capte tout (le filtrage se fait par handler)

# Références de handlers (pour éviter les doublons si module ré-importé)
_console_handler: logging.Handler | None = None
_file_handler: RotatingFileHandler | None = None
_silence_handler = logging.NullHandler()
_config_lock = threading.RLock()


# ------------------------------------------------------------
# Handlers (console + fichier)
# ------------------------------------------------------------
def _build_console_handler(console_level_name: str) -> logging.Handler:
    """
    Console : affiche [timestamp] LEVEL - message
    Le niveau (DEBUG/INFO/...) vient d'options.conf
    """
    if sys.platform == "win32":
        try:
            if hasattr(sys.stderr, "reconfigure"):
                sys.stderr.reconfigure(encoding="utf-8", errors="replace")
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    level = getattr(logging, console_level_name.upper(), logging.INFO)
    h = logging.StreamHandler()
    h.setLevel(level)
    h.setFormatter(logging.Formatter('[%(levelname)s] - %(message)s'))
    return h


def _logging_base_dir() -> str:
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _log_file_path(config) -> str:
    name = config["file_name"].strip()
    if not name or name in {".", ".."} or any(c in name for c in '/\\'):
        raise ValueError("Le nom du journal doit être un nom de fichier sans dossier.")
    directory = config["dir"].strip()
    if not directory:
        raise ValueError("Le dossier des journaux ne peut pas être vide.")
    return os.path.abspath(os.path.join(_logging_base_dir(), directory, name))


def _build_file_handler(file_path=None, level_name="DEBUG") -> RotatingFileHandler:
    """Journal configurable avec rotation de deux archives de 5 Mo."""
    if file_path is None:
        file_path = os.path.join(_logging_base_dir(), "logs", "add_dub.log")
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    h = RotatingFileHandler(
        file_path,
        maxBytes=5_000_000,   # ~5Mo
        backupCount=2,        # courant + .1 + .2 = 3 fichiers
        encoding="utf-8"
    )
    h.setLevel(getattr(logging, level_name.upper(), logging.DEBUG))
    h.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s:%(lineno)d - %(message)s'))
    return h


def reload_config() -> None:
    """Applique options.conf sans perdre les anciens handlers en cas d'échec.

    Le nouveau fichier est ouvert avant de détacher l'ancien. Un simple
    changement de niveau conserve le même fichier ouvert.
    """
    global _console_handler, _file_handler
    with _config_lock:
        config = _read_logging_config()
        new_file = None
        new_console = None
        try:
            if config["file_enable"]:
                path = _log_file_path(config)
                if (_file_handler is not None
                        and os.path.normcase(_file_handler.baseFilename) == os.path.normcase(path)):
                    new_file = _file_handler
                else:
                    new_file = _build_file_handler(path, config["file_level"])
            if config["console_enable"]:
                new_console = _console_handler or _build_console_handler(config["console_level"])
        except Exception:
            if new_file is not None and new_file is not _file_handler:
                new_file.close()
            raise

        for handler, level, default in (
                (new_file, config["file_level"], logging.DEBUG),
                (new_console, config["console_level"], logging.INFO)):
            if handler is not None:
                handler.setLevel(getattr(logging, level.upper(), default))

        for old, new in ((_file_handler, new_file), (_console_handler, new_console)):
            if old is new:
                continue
            if new is not None:
                logger.addHandler(new)
            if old is not None:
                logger.removeHandler(old)
                old.close()
        _file_handler, _console_handler = new_file, new_console
        # Sans handler, logging.lastResort réafficherait WARNING/ERROR en
        # console, même lorsque l'utilisateur a désactivé tous les journaux.
        if new_file is None and new_console is None:
            logger.addHandler(_silence_handler)
        else:
            logger.removeHandler(_silence_handler)


def _ensure_handlers_initialized() -> None:
    reload_config()


_ensure_handlers_initialized()


# ------------------------------------------------------------
# Utilitaires de contrôle (si besoin de forcer en code)
# ------------------------------------------------------------
def set_console_level(level_name: str) -> None:
    """Change dynamiquement le niveau de la console (ex: 'DEBUG' ↔ 'INFO')."""
    global _console_handler
    if _console_handler is None:
        return
    level = getattr(logging, level_name.upper(), logging.INFO)
    _console_handler.setLevel(level)


def set_console_enabled(enabled: bool) -> None:
    """Active/désactive totalement l'affichage console (indépendamment d'options.conf)."""
    global _console_handler
    if enabled and _console_handler is None:
        _, level = _read_console_config()
        _console_handler = _build_console_handler(level)
        logger.addHandler(_console_handler)
    elif (not enabled) and _console_handler is not None:
        logger.removeHandler(_console_handler)
        _console_handler.close()
        _console_handler = None


def is_console_enabled() -> bool:
    """True si un handler console est actuellement attaché au logger."""
    return any(isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler)
               for h in logger.handlers)


def enable_debug(enabled: bool) -> None:
    """Raccourci : passe la console en DEBUG (True) ou INFO (False)."""
    set_console_level("DEBUG" if enabled else "INFO")


def quiet_third_party() -> None:
    """Réduit le bruit de libs tierces trop bavardes."""
    for name in ("urllib3", "asyncio", "tqdm"):
        logging.getLogger(name).setLevel(logging.WARNING)


def want_progress() -> bool:
    """
    Indique si on peut afficher des barres de progression (tty + console active).
    Utile pour décider d'afficher tqdm ou un pourcentage.
    """
    return sys.stdout.isatty() and is_console_enabled()


# ------------------------------------------------------------
# Représentation compacte pour les paramètres/résultats volumineux
# ------------------------------------------------------------
def _safe_repr(value, *, max_len: int = 200, max_items: int = 10):
    """
    Représente proprement un objet dans les logs :
      - tronque les longues chaînes (md5 court inclus),
      - limite la taille des listes/dicos,
      - évite d'inonder les logs avec des blobs énormes.
    """
    try:
        if isinstance(value, str):
            if len(value) <= max_len:
                return repr(value)
            digest = hashlib.md5(value.encode("utf-8")).hexdigest()[:8]
            preview = value[:max_len].replace("\n", "\\n")
            return f"'{preview}...'(len={len(value)}, md5={digest})"

        if isinstance(value, (list, tuple)):
            head = [_safe_repr(v, max_len=max_len // 2, max_items=max_items // 2) for v in value[:max_items]]
            openb, closeb = ("[", "]") if isinstance(value, list) else ("(", ")")
            tail = ", ..."+closeb if len(value) > max_items else closeb
            return f"{openb}{', '.join(head)}{tail}"

        if isinstance(value, dict):
            keys = list(value.keys())[:max_items]
            items = [f"{repr(k)}: {_safe_repr(value[k], max_len=max_len // 2, max_items=max_items // 2)}" for k in keys]
            more = ", ..." if len(value) > max_items else ""
            return "{" + ", ".join(items) + more + "}"

        if isinstance(value, (bytes, bytearray)):
            return f"<{type(value).__name__} len={len(value)}>"

        text = repr(value)
        if len(text) > max_len:
            return f"{text[:max_len]}...(len={len(text)})"
        return text
    except Exception:
        return f"<unrepr {type(value).__name__}>"


# ------------------------------------------------------------
# Décorateurs
# ------------------------------------------------------------


def log_call(
    _func=None,
    *,
    include: set[str] | None = None,
    exclude: set[str] | None = None,
    show_result: bool = True,
    max_len: int = 200,
    max_items: int = 10
):
    def _decorator(func):
        if inspect.iscoroutinefunction(func):
            @wraps(func)
            async def _aw(*args, **kwargs):
                sig = inspect.signature(func)
                bound = sig.bind_partial(*args, **kwargs); bound.apply_defaults()
                parts = []
                for name, val in bound.arguments.items():
                    if include is not None and name not in include: continue
                    if exclude is not None and name in exclude: continue
                    parts.append(f"{name}={_safe_repr(val, max_len=max_len, max_items=max_items)}")
                logger.debug(f"→ {func.__name__}({', '.join(parts)})")
                try:
                    result = await func(*args, **kwargs)
                    if show_result:
                        logger.debug(f"← {func.__name__} -> {_safe_repr(result, max_len=max_len, max_items=max_items)}")
                    else:
                        logger.debug(f"← {func.__name__}")
                    return result
                except Exception as e:
                    logger.exception(f"‼ Erreur dans {func.__name__} : {e}")
                    raise
            return _aw
        else:
            @wraps(func)
            def _w(*args, **kwargs):
                sig = inspect.signature(func)
                bound = sig.bind_partial(*args, **kwargs); bound.apply_defaults()
                parts = []
                for name, val in bound.arguments.items():
                    if include is not None and name not in include: continue
                    if exclude is not None and name in exclude: continue
                    parts.append(f"{name}={_safe_repr(val, max_len=max_len, max_items=max_items)}")
                logger.debug(f"→ {func.__name__}({', '.join(parts)})")
                try:
                    result = func(*args, **kwargs)
                    if show_result:
                        logger.debug(f"← {func.__name__} -> {_safe_repr(result, max_len=max_len, max_items=max_items)}")
                    else:
                        logger.debug(f"← {func.__name__}")
                    return result
                except Exception as e:
                    logger.exception(f"‼ Erreur dans {func.__name__} : {e}")
                    raise
            return _w
    if _func is not None and callable(_func):
        return _decorator(_func)
    return _decorator


def log_time(_func=None):
    """
    Durée en console seulement ("X.XXX s"), compatible sync/async.
    """
    def _decorator(func):
        if inspect.iscoroutinefunction(func):
            @wraps(func)
            async def _aw(*args, **kwargs):
                start = time.perf_counter()
                try:
                    return await func(*args, **kwargs)
                finally:
                    seconds = time.perf_counter() - start
                    if is_console_enabled():
                        print(f"{seconds:.3f} s")
            return _aw
        else:
            @wraps(func)
            def _w(*args, **kwargs):
                start = time.perf_counter()
                try:
                    return func(*args, **kwargs)
                finally:
                    seconds = time.perf_counter() - start
                    if is_console_enabled():
                        print(f"{seconds:.3f} s")
            return _w
    if _func is not None and callable(_func):
        return _decorator(_func)
    return _decorator
