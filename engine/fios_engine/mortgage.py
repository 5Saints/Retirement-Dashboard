"""Primary-mortgage payoff-boundary rule (PRD Section 4.10, CR-002).

Until rate/payment/maturity are supplied, the $100,000 baseline balance is modeled as
linearly extinguished from the consumption residual by the payoff boundary date (default
2031-12-31, one year before the 2032 baseline retirement date), with a placeholder flag.
When real amortization terms arrive, they replace the placeholder and payoff must complete
before retirement; if supplied terms would carry a balance past retirement, the engine
raises a warning rather than silently extending the payoff.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class MortgagePayoffPlan:
    monthly_payment: Decimal
    is_placeholder: bool
    warning: str | None = None


def placeholder_payoff_plan(
    opening_balance: Decimal, current_date: date, payoff_boundary_date: date
) -> MortgagePayoffPlan:
    """Even (non-amortizing) monthly paydown from `current_date` to
    `payoff_boundary_date`, used only while real loan terms are unsupplied."""
    months = (
        (payoff_boundary_date.year - current_date.year) * 12
        + (payoff_boundary_date.month - current_date.month)
    )
    if months <= 0:
        raise ValueError("payoff_boundary_date must be after current_date")
    return MortgagePayoffPlan(
        monthly_payment=opening_balance / Decimal(months),
        is_placeholder=True,
    )


def balance_after_months(opening_balance: Decimal, monthly_payment: Decimal, months_elapsed: int) -> Decimal:
    remaining = opening_balance - monthly_payment * Decimal(months_elapsed)
    return remaining if remaining > 0 else Decimal("0")


def amortized_payoff_plan(
    monthly_payment: Decimal,
    maturity_date: date,
    retirement_date: date,
) -> MortgagePayoffPlan:
    """Real amortization terms. Flags (does not silently swallow) a maturity that falls
    after the retirement date, per CR-002."""
    warning = None
    if maturity_date > retirement_date:
        warning = (
            f"supplied mortgage maturity {maturity_date} falls after retirement date "
            f"{retirement_date}; balance would not be fully retired before retirement"
        )
    return MortgagePayoffPlan(
        monthly_payment=monthly_payment,
        is_placeholder=False,
        warning=warning,
    )
