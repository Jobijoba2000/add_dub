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

def _ask_target_lang(prompt: str, default: str) -> str:
    while True:
        val = ask_string(prompt, default=default).strip().lower()
        if len(val) == 2 and val.isalpha():
            return val
        print(t("cli_lang_code_invalid"))


def _ask_source_lang(prompt: str, default: str) -> str | None:
    while True:
        val = ask_string(prompt, default=default).strip().lower()
        if val in ("auto", "none", ""):
            return None
        if len(val) == 2 and val.isalpha():
            return val
        print(t("cli_lang_source_invalid"))


def ask_translation_options(base_opts, opts: Dict[str, OptEntry]):
    """
    Demande si on veut traduire, et si oui, vers quelle langue et avec quel moteur.
    Retourne la clé (do_trans, trans_to, trans_from, trans_engine).
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
    
    trans_to = (base_opts.translate_to or "fr").strip().lower()[:2]
    trans_from = base_opts.translate_from
    trans_engine = (getattr(base_opts, "translation_engine", "ctranslate2") or "ctranslate2").strip().lower()

    if do_trans:
        # 2. Target lang
        entry_to = opts.get("translate_to")
        should_ask_to = True
        if entry_to and not entry_to.display:
            should_ask_to = False
            raw_to = str(entry_to.value).strip().lower()
            if len(raw_to) >= 2 and raw_to[:2].isalpha():
                trans_to = raw_to[:2]
            else:
                trans_to = "fr"
        
        if should_ask_to:
            trans_to = _ask_target_lang(
                t("cli_ask_translate_lang", default=trans_to),
                default=trans_to
            )
        
        # 3. Source lang (optional)
        entry_from = opts.get("translate_from")
        should_ask_from = True
        if entry_from and not entry_from.display:
            should_ask_from = False
            val = str(entry_from.value).strip().lower()
            if val in ("none", "auto", ""):
                trans_from = None
            elif len(val) >= 2 and val[:2].isalpha():
                trans_from = val[:2]
            else:
                trans_from = None
        
        if should_ask_from:
            src_def = base_opts.translate_from or "auto"
            trans_from = _ask_source_lang(
                t("cli_ask_translate_from", default=src_def),
                default=src_def
            )

        # 4. Translation engine
        entry_eng = opts.get("translation_engine")
        should_ask_eng = True
        if entry_eng and not entry_eng.display:
            should_ask_eng = False
            eng_val = str(entry_eng.value).strip().lower()
            if eng_val in ("google", "ctranslate2"):
                trans_engine = eng_val

        if should_ask_eng:
            engine_choices = [
                ("ctranslate2", t("cli_trans_engine_1").strip()),
                ("google", t("cli_trans_engine_2").strip()),
            ]
            chosen_eng = ask_choice(
                t("cli_trans_engine_choice"),
                engine_choices,
                default_val=trans_engine
            )
            if chosen_eng:
                trans_engine = chosen_eng

    return do_trans, trans_to, trans_from, trans_engine


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
