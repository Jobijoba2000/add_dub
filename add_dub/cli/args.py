# add_dub/cli/args.py
# 4 espaces d'indentation
from __future__ import annotations

import argparse
from typing import Tuple


def parse_args(argv: list[str]) -> Tuple[argparse.Namespace, list[str]]:
    """
    Parse uniquement ce qui nous intéresse maintenant, sans casser l'existant.
    On utilise parse_known_args pour ignorer les flags futurs tant qu'ils ne sont pas implémentés.

    Retourne (args, unknown) où:
        - args: Namespace avec les options reconnues (ex: --interactive)
        - unknown: liste des autres tokens laissés de côté (pour évolution ultérieure)
    """
    parser = argparse.ArgumentParser(
        prog="add_dub",
        add_help=True,
        description="add_dub — lance l'outil (interactif par défaut)."
    )

    # Modes (pour l’instant on ne branche réellement que --interactive)
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Force le mode interactif (comportement actuel)."
    )

    # On accepte déjà ces options pour l’avenir, sans les utiliser tout de suite.
    parser.add_argument(
        "--batch",
        action="store_true",
        help="(Réservé) Mode non-interactif. Ignoré tant que non implémenté."
    )
    parser.add_argument(
        "--files",
        nargs="+",
        metavar="FICHIER",
        help="(Réservé) Fichiers à traiter en mode batch. Ignoré tant que non implémenté."
    )

    # IMPORTANT: ne pas lever d'erreur sur les options non encore gérées
    args, unknown = parser.parse_known_args(argv)
    return args, unknown


def want_interactive(args: argparse.Namespace) -> bool:
    """
    Décide si on doit lancer l'interactif.
    Aujourd'hui: interactif par défaut, ou si --interactive est présent.
    """
    if getattr(args, "interactive", False):
        return True
    # Tant que le batch n'est pas implémenté, on reste en interactif par défaut.
    return True
