"""Anchored-real retirement spending rule (PRD Section 4.9, CR-003).

The $300,000 target is a real level anchored at 2032 dollars. For any candidate retirement
year Y: first_year_spending(Y) = 300_000 * (1 + i) ** (Y - 2032). The engine must never
inflate the anchor forward from 2026 to 2032 -- 2032 is the anchor year, not the base year.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .models import ExpenseCategory

ANCHOR_YEAR = 2032
ANCHOR_TOTAL = Decimal("300000")


def first_year_spending(retirement_year: int, inflation_rate: Decimal) -> Decimal:
    exponent = retirement_year - ANCHOR_YEAR
    return ANCHOR_TOTAL * (1 + inflation_rate) ** exponent


def scaled_categories(
    categories: list[ExpenseCategory], retirement_year: int, inflation_rate: Decimal
) -> dict[str, Decimal]:
    """Scale each category proportionally to first_year_spending / ANCHOR_TOTAL,
    preserving the essential/discretionary split at any retirement date."""
    target = first_year_spending(retirement_year, inflation_rate)
    scale = target / ANCHOR_TOTAL
    return {c.name: c.anchor_amount * scale for c in categories}


@dataclass(frozen=True)
class SpendingSchedule:
    retirement_year: int
    first_year_total: Decimal
    inflation_rate: Decimal

    def spending_in_year(self, year: int) -> Decimal:
        """Spending grows at `inflation_rate` per year *after* retirement begins from
        the first-year value -- this is a separate step from the anchor conversion."""
        if year < self.retirement_year:
            raise ValueError("spending_in_year is only defined at/after retirement")
        return self.first_year_total * (1 + self.inflation_rate) ** (year - self.retirement_year)


def build_schedule(retirement_year: int, inflation_rate: Decimal) -> SpendingSchedule:
    return SpendingSchedule(
        retirement_year=retirement_year,
        first_year_total=first_year_spending(retirement_year, inflation_rate),
        inflation_rate=inflation_rate,
    )
