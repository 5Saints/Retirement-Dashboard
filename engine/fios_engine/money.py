"""Decimal helpers. All financial amounts in FIOS are `Decimal` — never `float`
(PRD Section 11: "Financial amounts should use decimal types, never floating-point types.").
"""

from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def D(value) -> Decimal:
    """Convert an int/str/Decimal into a full-precision Decimal. Never accepts float,
    since a float literal already carries binary rounding error before conversion."""
    if isinstance(value, float):
        raise TypeError(
            f"refusing to construct Decimal from float {value!r}; "
            "pass an int, str, or Decimal instead"
        )
    return Decimal(value)


def to_cents(value: Decimal) -> Decimal:
    """Round to the nearest cent. Only applied when a value is reported at period
    close — intermediate arithmetic stays at full precision (calculation-spec.md)."""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def to_dollars(value: Decimal) -> Decimal:
    """Round to the nearest whole dollar, for display-grade figures such as the
    salary projection (PRD Section 4.2 reports $351,363, not $351,362.61)."""
    return value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
