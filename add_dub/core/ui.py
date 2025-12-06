from typing import Protocol, Optional
from add_dub.helpers.console import ask_yes_no
from add_dub.i18n import t

class UIInterface(Protocol):
    def message(self, text: str) -> None:
        """Display a standard message to the user."""
        ...

    def error(self, text: str) -> None:
        """Display an error message to the user."""
        ...

    def ask_yes_no(self, question: str, default: bool = False) -> bool:
        """Ask a yes/no question."""
        ...

    def ask_float(self, prompt: str, default: float) -> float:
        """Ask for a float value."""
        ...

    def progress(self, percent: float) -> None:
        """Report progress (0.0 to 100.0)."""
        ...

class ConsoleUI:
    def message(self, text: str) -> None:
        print(text)

    def error(self, text: str) -> None:
        # Using print for now to match existing behavior, could use logger or stderr
        print(text)

    def ask_yes_no(self, question: str, default: bool = False) -> bool:
        return ask_yes_no(question, default=default)

    def ask_float(self, prompt: str, default: float) -> float:
        raw = input(t("ui_prompt_default", prompt=prompt, default=default)).strip()
        if not raw:
            return default
        try:
            return float(raw)
        except Exception:
            print(t("ui_invalid_value"))
            return default

    def progress(self, percent: float) -> None:
        # Simple console progress, maybe just print or overwrite line
        # For now, let's match the translation worker behavior if possible,
        # or just print if it's a significant step.
        # The translation worker uses \r to overwrite.
        print(f"Progress: {percent:.1f}%", end="\r", flush=True)
