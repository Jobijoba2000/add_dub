from add_dub.i18n import t

def ask_mode():
    ans = input("\nMode (A)uto / (M)anuel ? [A]: ").strip().lower()
    return "manual" if ans.startswith("m") else "auto"

def ask_yes_no(prompt_txt, default_no=True):
    default = "n" if default_no else "o"
    s = input(f"{prompt_txt} (o/n) [{default}]: ").strip().lower()
    if s == "":
        return not default_no
    return s.startswith("o") or s == "y"

def ask_float(prompt_txt, default):
    s = input(f"{prompt_txt} [{default}]: ").strip()
    try:
        return float(s) if s != "" else float(default)
    except ValueError:
        print(t("ui_invalid_value"))
        return float(default)

def ask_int(prompt_txt, default):
    s = input(f"{prompt_txt} [{default}]: ").strip()
    try:
        return int(s) if s != "" else int(default)
    except ValueError:
        print(t("ui_invalid_value"))
        return int(default)

def ask_str(prompt_txt, default):
    s = input(f"{prompt_txt} [{default}]: ").strip()
    return s if s != "" else default

# Helper générique (place-la là où tu appelles ask_float/ask_int/ask_str)
def ask_option(key: str, opts, kind: str, prompt: str, default):
    """
    key   : nom de l’option (ex. "db", "offset", "bg", "tts")
    opts  : dictionnaire renvoyé par load_options()
    kind  : "float" | "int" | "str"
    prompt: texte de la question à afficher si on doit demander
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
    return ask_str(prompt, str(default))
