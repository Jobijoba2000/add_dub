# add_dub/gui/ui_adapter.py
from __future__ import annotations

import queue
from typing import Optional


class GuiUIAdapter:
    """
    Implémentation 100 % thread-safe de UIInterface pour l'interface graphique Tkinter.
    Toutes les interactions sont transmises via une file d'attente (Queue)
    dépilée en continu sur le thread principal de l'UI.
    """

    def __init__(self, event_queue: queue.Queue):
        self.queue = event_queue

    def message(self, text: str) -> None:
        clean = str(text).strip()
        if clean:
            self.queue.put(("message", clean))

    def error(self, text: str) -> None:
        clean = str(text).strip()
        if clean:
            self.queue.put(("error", clean))

    def progress(self, percent: float) -> None:
        pct = max(0.0, min(100.0, float(percent)))
        self.queue.put(("progress", pct))

    def ask_yes_no(self, question: str, default: bool = False) -> bool:
        """
        Demande interactive bloquante transmise au thread principal via Queue.
        """
        response_q: queue.Queue[bool] = queue.Queue(maxsize=1)
        self.queue.put(("ask_yes_no", (response_q, question, default)))
        return response_q.get()

    def ask_float(self, prompt: str, default: float) -> float:
        return float(default)
