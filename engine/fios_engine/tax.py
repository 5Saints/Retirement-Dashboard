"""Effective-rate tax placeholders (PRD Section 7.4).

The MVP tax engine uses flat effective rates; the architecture permits later replacement
with a bracket-based federal/state module (Phase 5). Every rate here is a `Valued` with
status PLACEHOLDER pending CPA confirmation (CL-2) -- never hidden inside a return
assumption (Section 7.4: "Never hide a tax assumption inside a return assumption").
"""

from __future__ import annotations

from decimal import Decimal

from .models import Status, Valued

LIQUIDITY_EVENT_TAX_RATE = Valued(
    Decimal("0.30"), Status.PLACEHOLDER, "unresolved pending CPA confirmation"
)

TAX_DEFERRED_DISTRIBUTION_TAX_RATE = Valued(
    Decimal("0.25"), Status.PLACEHOLDER, "unresolved pending CPA confirmation (CL-2)"
)


def estimated_tax(gross: Decimal, rate: Valued) -> Decimal:
    return gross * rate.value
