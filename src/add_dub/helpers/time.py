# src/add_dub/helpers/time.py

import time


def measure_duration(func, *args, **kwargs):
    """
    Exécute une fonction et retourne (résultat, durée formatée en secondes).
    """
    start = time.perf_counter()
    result = func(*args, **kwargs)
    end = time.perf_counter()
    duration = f"{end - start:.3f}s"
    print(duration)
    return result
