# add_dub/logger.py
# ------------------------------------------------------------
# Logger central du projet :
# - Lit la config console depuis options.conf via opts_loader
# - Écrit TOUT (DEBUG/INFO/...) dans un fichier rotatif (3x~5Mo)
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
from functools import wraps
from logging.handlers import RotatingFileHandler
from add_dub.config.opts_loader import load_options, OptEntry



# ------------------------------------------------------------
# Lecture des réglages console depuis options.conf
#   [logging]
#   console_enable = true|false
#   console_level  = DEBUG|INFO|WARNING|ERROR|CRITICAL
# ------------------------------------------------------------
def _read_console_config():
    opts = load_options()

    def _val(key, default):
        v = opts.get(key)
        return v.value if isinstance(v, OptEntry) else default

    enable = bool(_val("logging.console_enable", True))
    level = str(_val("logging.console_level", "DEBUG")).upper()
    return enable, level


# ------------------------------------------------------------
# Logger central "add_dub"
# ------------------------------------------------------------
logger = logging.getLogger("add_dub")
logger.setLevel(logging.DEBUG)  # on capte tout (le filtrage se fait par handler)

# Références de handlers (pour éviter les doublons si module ré-importé)
_console_handler: logging.Handler | None = None
_file_handler: RotatingFileHandler | None = None


# ------------------------------------------------------------
# Handlers (console + fichier)
# ------------------------------------------------------------
def _build_console_handler(console_level_name: str) -> logging.Handler:
    """
    Console : affiche [timestamp] LEVEL - message
    Le niveau (DEBUG/INFO/...) vient d'options.conf
    """
    level = getattr(logging, console_level_name.upper(), logging.INFO)
    h = logging.StreamHandler()
    h.setLevel(level)
    h.setFormatter(logging.Formatter('[%(levelname)s] - %(message)s'))
    return h


def _build_file_handler() -> RotatingFileHandler:
    """
    Fichier : add_dub/logs/add_dub.log + rotation (2 archives)
    Format verbeux (timestamp + niveau + logger:ligne + message)
    """
    log_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(log_dir, exist_ok=True)
    file_path = os.path.join(log_dir, "add_dub.log")

    h = RotatingFileHandler(
        file_path,
        maxBytes=5_000_000,   # ~5Mo
        backupCount=2,        # courant + .1 + .2 = 3 fichiers
        encoding="utf-8"
    )
    h.setLevel(logging.DEBUG)  # on garde tout dans le fichier
    h.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s:%(lineno)d - %(message)s'))
    return h


def _ensure_handlers_initialized() -> None:
    """
    Création/attachement unique des handlers (fichier + console).
    Relit options.conf pour savoir si la console est activée et à quel niveau.
    """
    global _console_handler, _file_handler

    # FICHIER (toujours actif)
    if _file_handler is None:
        _file_handler = _build_file_handler()
        logger.addHandler(_file_handler)

    # CONSOLE (activable via options.conf)
    enable_console, console_level = _read_console_config()
    if enable_console and _console_handler is None:
        _console_handler = _build_console_handler(console_level)
        logger.addHandler(_console_handler)
    if (not enable_console) and _console_handler is not None:
        logger.removeHandler(_console_handler)
        _console_handler = None


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
            import hashlib as _h
            digest = _h.md5(value.encode("utf-8")).hexdigest()[:8]
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
