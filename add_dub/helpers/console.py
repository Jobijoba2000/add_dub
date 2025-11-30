# add_dub/helpers/console.py
from add_dub.i18n import t

def ask_string(prompt, default=""):
    """
    Pose une question (prompt) et retourne la chaîne saisie.
    Si vide, retourne default.
    """
    if default:
        final_prompt = t("ui_prompt_default", prompt=prompt, default=default)
    else:
        final_prompt = f"{prompt}: "
    
    val = input(final_prompt).strip()
    if not val:
        return default
    return val

def ask_int(prompt, default=0):
    while True:
        val_str = ask_string(prompt, str(default))
        try:
            return int(val_str)
        except ValueError:
            print(t("ui_invalid_value"))

def ask_float(prompt, default=0.0):
    while True:
        val_str = ask_string(prompt, str(default))
        try:
            return float(val_str)
        except ValueError:
            print(t("ui_invalid_value"))

def ask_yes_no(prompt, default=False):
    """
    Retourne bool.
    default=True => [Y/n], default=False => [y/N]
    """
    if default:
        y_n = "O/n"
    else:
        y_n = "o/N"
    
    final_prompt = t("ui_prompt_yes_no", prompt=prompt, default=y_n)
    val = input(final_prompt).strip().lower()
    if not val:
        return default
    if val.startswith("o") or val.startswith("y"):
        return True
    if val.startswith("n"):
        return False
    return default
