"""Money and date formatting.

All money is `Decimal`. Rounding is ROUND_HALF_UP to the centavo ("arredondamento
comercial"), applied per line. BRL is formatted by hand (no `locale`), because the
pt_BR locale is often missing and `setlocale` raises.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def to_money(value: str | int | float | Decimal) -> Decimal:
    """Parse a CSV value (e.g. "599.9") into a 2-place Decimal without float noise."""
    if isinstance(value, float):
        value = repr(value)
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def round_money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def apply_discount(price: Decimal, percent: Decimal | int) -> Decimal:
    """Price after a percentage discount, rounded half-up to the centavo."""
    factor = (Decimal(100) - Decimal(percent)) / Decimal(100)
    return round_money(price * factor)


def fmt_brl(value: Decimal) -> str:
    """Format as Brazilian Real: `R$ 1.967,18`."""
    value = round_money(value)
    sign = "-" if value < 0 else ""
    integer, _, cents = f"{abs(value):.2f}".partition(".")
    groups = []
    while len(integer) > 3:
        groups.insert(0, integer[-3:])
        integer = integer[:-3]
    groups.insert(0, integer)
    return f"{sign}R$ {'.'.join(groups)},{cents}"


def fmt_date(value: date | datetime) -> str:
    """Format as `dd/mm/aaaa`."""
    return value.strftime("%d/%m/%Y")
