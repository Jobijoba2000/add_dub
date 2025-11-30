# add_dub/cli/ui.py
from typing import Dict, Any, Optional
from add_dub.config.opts_loader import OptEntry
from add_dub.helpers.console import ask_int, ask_float, ask_string, ask_yes_no
from add_dub.i18n import t

def ask_option(
    key: str,
    opts: Dict[str, OptEntry],
    kind: str,
    prompt: str,
    default: Any
) -> Any:
    """
    Demande une option à l'utilisateur si elle n'est pas définie dans options.conf (ou si display=True).
    
    key: clé dans options.conf (ex: "ducking")
    opts: dictionnaire retourné par load_options()
    kind: type attendu ("str", "int", "float")
    prompt: question posée
    default: valeur courante (base_opts.*) à utiliser si on ne pose pas la question,
             ou comme repli si la clé n'existe pas dans options.conf
    """
    entry = opts.get(key)

    # Chemin silencieux : valeur dans options.conf SANS 'd' => on ne demande rien,
    # on renvoie la valeur de base (default), pour préserver les re-tests.
    if entry and not entry.display:
        if kind == "int":
            return int(default)
        if kind == "float":
            return float(default)
        return str(default)

    # Chemin interactif : on pose la question avec un défaut pertinent
    
    if kind == "int":
        return ask_int(prompt, int(default))
    if kind == "float":
        return ask_float(prompt, float(default))
    
    # kind == "str"
    return ask_string(prompt, str(default))

def ask_translation_options(base_opts):
    """
    Demande si on veut traduire, et si oui, vers quelle langue.
    Met à jour base_opts et retourne les valeurs choisies.
    """
    # 1. Ask translate?
    do_trans = ask_yes_no(t("cli_ask_translate"), default=base_opts.translate)
    base_opts.translate = do_trans
    
    if do_trans:
        # 2. Target lang
        target = ask_string(t("cli_ask_translate_lang", default=base_opts.translate_to), default=base_opts.translate_to)
        base_opts.translate_to = target
        
        # 3. Source lang (optional)
        src_def = base_opts.translate_from or ""
        src = ask_string(t("cli_ask_translate_from", default=src_def if src_def else "auto"), default=src_def)
        if src and src.lower() != "auto":
            base_opts.translate_from = src
        else:
            base_opts.translate_from = None
            
    return base_opts.translate, base_opts.translate_to, base_opts.translate_from
