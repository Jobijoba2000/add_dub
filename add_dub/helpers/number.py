# add_dub/core/pipeline.py

from decimal import Decimal, InvalidOperation
from typing import Union

def int_to_scaled_str(value: int, multiplier: Union[str, float, Decimal] = "0.001") -> str:
    """
    Convertit un entier en chaîne après multiplication par un coefficient.
    - value : entier source (ex. millisecondes).
    - multiplier : coefficient d'échelle (ex. "0.001" pour ms -> s).
      Peut être str, float ou Decimal. Le nombre de décimales du résultat
      suit celui du coefficient (ex. "0.001" -> 3 décimales).

    Exemples :
        int_to_scaled_str(2000)               -> "2.000"
        int_to_scaled_str(-37)                -> "-0.037"
        int_to_scaled_str(12345, "0.000001")  -> "0.012345"
        int_to_scaled_str(123, 1)             -> "123"
    """
    try:
        m = Decimal(str(multiplier))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"multiplier invalide : {multiplier!r}") from exc

    if m == 0:
        raise ValueError("multiplier ne doit pas être nul")

    sign = "-" if value < 0 else ""
    mag = abs(int(value))

    scaled = Decimal(mag) * m
    decimals = max(0, -m.as_tuple().exponent)  # nb de décimales du coefficient
    quant = Decimal("1").scaleb(-decimals) if decimals else Decimal("1")

    return f"{sign}{scaled.quantize(quant)}"
