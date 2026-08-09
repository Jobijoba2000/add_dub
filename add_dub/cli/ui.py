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

def ask_translation_options(base_opts, opts: Dict[str, OptEntry]):
    """
    Demande si on veut traduire, et si oui, vers quelle langue.
    Retourne la clé (do_trans, trans_to, trans_from).
    """
    # 1. Ask translate?
    entry_trans = opts.get("translate")
    should_ask_trans = True
    do_trans = base_opts.translate
    if entry_trans and not entry_trans.display:
        should_ask_trans = False
        do_trans = bool(entry_trans.value)
    
    if should_ask_trans:
        do_trans = ask_yes_no(t("cli_ask_translate"), default=base_opts.translate)
    
    trans_to = base_opts.translate_to
    trans_from = base_opts.translate_from

    if do_trans:
        # 2. Target lang
        entry_to = opts.get("translate_to")
        should_ask_to = True
        if entry_to and not entry_to.display:
            should_ask_to = False
            trans_to = str(entry_to.value)
        
        if should_ask_to:
            trans_to = ask_string(t("cli_ask_translate_lang", default=base_opts.translate_to), default=base_opts.translate_to)
        
        # 3. Source lang (optional)
        entry_from = opts.get("translate_from")
        should_ask_from = True
        if entry_from and not entry_from.display:
            should_ask_from = False
            val = str(entry_from.value).strip()
            if val.lower() == "none" or val.lower() == "auto" or not val:
                trans_from = None
            else:
                trans_from = val
        
        if should_ask_from:
            src_def = base_opts.translate_from or ""
            src = ask_string(t("cli_ask_translate_from", default=src_def if src_def else "auto"), default=src_def)
            if src and src.lower() != "auto":
                trans_from = src
            else:
                trans_from = None

    return do_trans, trans_to, trans_from

def ask_choice(
    prompt: str,
    choices: list[tuple[str, str]],
    default_val: str | None = None
) -> str | None:
    """
    Affiche une liste numérotée de choix et retourne la valeur choisie.
    
    choices: liste de tuples (valeur, label). Ex: [("aac", "AAC"), ("mp3", "MP3")]
    default_val: valeur par défaut si l'utilisateur fait Entrée vide.
                 Si None, Entrée vide retourne None (pas de changement).
    
    Retourne la 'valeur' sélectionnée.
    """
    print(f"\n{prompt}")
    
    # Affichage
    for idx, (val, label) in enumerate(choices, start=1):
        print(f"    {idx}) {label}")
        
    def_label = ""
    if default_val is not None:
        # Trouver le label du default si possible
        found = next((lbl for v, lbl in choices if v == default_val), default_val)
        def_label = f" [{found}]"
        
    while True:
        raw = input(f"Choice{def_label}: ").strip()
        
        if not raw:
            return default_val
            
        try:
            idx = int(raw)
            if 1 <= idx <= len(choices):
                return choices[idx-1][0]
        except ValueError:
            pass
            
        print("Invalid choice.")
