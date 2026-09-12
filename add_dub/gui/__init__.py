"""Interface graphique ; chargement de Qt uniquement au lancement du mode GUI."""


def main(args):
    from .application import main as run
    return run(args)
