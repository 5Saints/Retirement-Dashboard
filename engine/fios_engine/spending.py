"""Anchored-real retirement spending rule (PRD Section 4.9, CR-003).

The $300,000 baseline target is a real level anchored at 2032 dollars -- the sum of the
household's own expense-category anchor amounts (Section 4.9's six-row table), not a
constant independent of them. For any candidate retirement year Y:
first_year_spending(Y) = anchor_total * (1 + i) ** (Y - 2032). The engine must never
inflate the anchor forward from 2026 to 2032 -- 2032 is the anchor year, not the base year.

`first_year_spending`/`build_schedule` take the household's `expense_categories` and sum
their `anchor_amount` rather than hardcoding $300,000, so a scenario that edits category
anchors (`scenario_library.reduce_discretionary_spending`, an increase-spending decision)
actually changes the spending the projection engine withdraws -- discovered as a real gap
via the Phase 4 Monte Carlo boundary tests (Section 20) that inflating a scenario's
category anchors had no effect on simulated outcomes, since the total was reading from a
disconnected module constant.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .models import ExpenseCategory

ANCHOR_YEAR = 2032


def _anchor_total(categories: list[ExpenseCategory]) -> Decimal:
    return sum((c.anchor_amount for c in categories), Decimal("0"))


def first_year_spending(
    categories: list[ExpenseCategory], retirement_year: int, inflation_rate: Decimal
) -> Decimal:
    exponent = retirement_year - ANCHOR_YEAR
    return _anchor_total(categories) * (1 + inflation_rate) ** exponent


def scaled_categories(
    categories: list[ExpenseCategory], retirement_year: int, inflation_rate: Decimal
) -> dict[str, Decimal]:
    """Scale each category proportionally to first_year_spending / anchor_total,
    preserving the essential/discretionary split at any retirement date."""
    anchor_total = _anchor_total(categories)
    target = first_year_spending(categories, retirement_year, inflation_rate)
    scale = target / anchor_total
    return {c.name: c.anchor_amount * scale for c in categories}


def essential_fraction(categories: list[ExpenseCategory]) -> Decimal:
    """Fraction of the anchored spending target that is essential (Section 4.9): fixed
    by the category anchor amounts, independent of retirement year or inflation, since
    scaling is proportional at any retirement date. Lives here (not retirement_tests.py,
    which re-exports it for backward compatibility) so projection.py's spending
    guardrails (Section 7.5, Phase 5) can use it without importing retirement_tests.py,
    which itself imports projection.py."""
    anchor_total = _anchor_total(categories)
    essential = sum((c.anchor_amount for c in categories if c.essential), Decimal("0"))
    return essential / anchor_total


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


def build_schedule(
    categories: list[ExpenseCategory], retirement_year: int, inflation_rate: Decimal
) -> SpendingSchedule:
    return SpendingSchedule(
        retirement_year=retirement_year,
        first_year_total=first_year_spending(categories, retirement_year, inflation_rate),
        inflation_rate=inflation_rate,
    )
