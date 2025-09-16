# src/add_dub/cli/ui.py
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
    except:
        print("Valeur invalide, on garde le défaut.")
        return float(default)

def ask_int(prompt_txt, default):
    s = input(f"{prompt_txt} [{default}]: ").strip()
    try:
        return int(s) if s != "" else int(default)
    except:
        print("Valeur invalide, on garde le défaut.")
        return int(default)

def ask_str(prompt_txt, default):
    s = input(f"{prompt_txt} [{default}]: ").strip()
    return s if s != "" else default
