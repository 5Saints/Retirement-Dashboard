"""Share-ledger sequencing across multiple liquidity events.

Price-path interpolation and single-event derivation live on `EquityPosition` /
`LiquidityEvent` in `models.py` (co-located with the data they operate on). This module
adds the one thing that isn't a property of a single event: walking an ordered list of
events against one equity position to produce the running share balance, since each
event's `shares_sold` must be checked against what remains *after* prior events.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .models import EquityPosition, LiquidityEvent, LiquidityEventResult


@dataclass(frozen=True)
class LedgerStep:
    event: LiquidityEvent
    result: LiquidityEventResult
    shares_remaining_after: Decimal


def run_share_ledger(
    position: EquityPosition,
    events: list[LiquidityEvent],
    retirement_date: date,
) -> list[LedgerStep]:
    """Apply liquidity events in chronological order (resolved date), returning the
    derived proceeds and running share balance after each. Raises if an event tries to
    sell more shares than remain."""

    ordered = sorted(events, key=lambda e: e.resolve_date(retirement_date))
    shares_remaining = position.share_quantity
    steps: list[LedgerStep] = []
    for event in ordered:
        if event.shares_sold > shares_remaining:
            raise ValueError(
                f"liquidity event sells {event.shares_sold} shares but only "
                f"{shares_remaining} remain"
            )
        result = event.derive(retirement_date)
        shares_remaining -= event.shares_sold
        steps.append(LedgerStep(event=event, result=result, shares_remaining_after=shares_remaining))
    return steps


def concentration_risk_index(equity_value: Decimal, denominator: Decimal) -> Decimal:
    """Equity value as a fraction of net worth or investable assets (Section 25).
    Returns 0 when denominator is 0 to avoid a division error on a fully-liquidated,
    zero-net-worth edge case."""
    if denominator == 0:
        return Decimal("0")
    return equity_value / denominator
