"""Share ledger and price-path mechanics (PRD Section 4.7, 4.7.1)."""

from datetime import date
from decimal import Decimal

import pytest

from fios_engine.models import (
    DateMode,
    EquityPosition,
    InterpolationMode,
    LiquidityEvent,
    PricePathAnchor,
    Status,
    Valued,
)


def make_position():
    return EquityPosition(
        description="Test equity",
        share_quantity=Decimal("100"),
        basis=None,
        anchors=[
            PricePathAnchor(date(2026, 1, 1), Decimal("10000"), Status.CONFIRMED),
            PricePathAnchor(date(2030, 1, 1), Decimal("20000"), Status.ASSUMPTION),
        ],
    )


def test_step_interpolation_uses_most_recent_anchor_at_or_before_date():
    position = make_position()

    assert position.resolve_price(date(2026, 1, 1)) == Decimal("10000")
    assert position.resolve_price(date(2027, 6, 1)) == Decimal("10000")
    assert position.resolve_price(date(2030, 1, 1)) == Decimal("20000")


def test_step_interpolation_holds_flat_after_last_anchor():
    position = make_position()
    assert position.resolve_price(date(2050, 1, 1)) == Decimal("20000")


def test_step_interpolation_before_first_anchor_uses_earliest_anchor():
    position = make_position()
    assert position.resolve_price(date(2020, 1, 1)) == Decimal("10000")


def test_geometric_interpolation_compounds_between_anchors():
    position = make_position()
    position.interpolation_mode = InterpolationMode.GEOMETRIC

    midpoint = date(2028, 1, 1)  # exactly halfway between 2026-01-01 and 2030-01-01
    price = position.resolve_price(midpoint)

    # geometric mean of 10000 and 20000 over a half span
    assert Decimal("14000") < price < Decimal("14400")


def test_equity_position_has_no_settable_dollar_value():
    """Appendix B: a standalone dollar valuation must be impossible to enter -- verified
    here by the absence of any such attribute on the model, per the plan's design choice
    to make this unrepresentable rather than runtime-reject it."""
    position = make_position()
    assert not hasattr(position, "value_override")
    assert not any(f == "value" for f in position.__dataclass_fields__)


def test_liquidity_event_cannot_oversell_shares():
    from fios_engine.equity import run_share_ledger

    position = make_position()
    tax_rate = Valued(Decimal("0.30"), Status.PLACEHOLDER)
    event = LiquidityEvent(
        equity_position=position,
        date_mode=DateMode.FIXED,
        shares_sold=Decimal("150"),  # more than the 100 shares held
        tax_rate=tax_rate,
        fixed_date=date(2026, 6, 1),
    )

    with pytest.raises(ValueError):
        run_share_ledger(position, [event], date(2032, 1, 1))
