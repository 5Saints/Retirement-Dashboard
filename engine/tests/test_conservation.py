"""Property test for the pre-retirement conservation identity (PRD Section 4.10, CR-002):
income == taxes + contributions + debt_service + implied_spending, every pre-retirement
period. This holds by construction since implied_spending is defined as the residual, but
the test guards against a future refactor accidentally breaking that construction."""

from decimal import Decimal

from fios_engine.projection import run_projection
from fios_engine.seed import build_baseline_scenario


def test_conservation_identity_every_pre_retirement_period():
    scenario = build_baseline_scenario()
    output = run_projection(scenario, terminal_age=60)

    pre_retirement_periods = [p for p in output.periods if not p.is_retired]
    assert len(pre_retirement_periods) > 0

    for period in pre_retirement_periods:
        lhs = period.gross_income
        rhs = (
            period.estimated_taxes
            + period.contributions_401k
            + period.debt_service
            + period.implied_pre_retirement_spending
        )
        assert lhs == rhs, f"conservation identity failed at {period.period_date}"


def test_liquidity_event_proceeds_never_fund_consumption():
    """Section 4.10: liquidity-event proceeds never fund consumption -- the residual
    applies to salary/bonus only. The month Event 1 fires, implied_spending should be
    computed purely from salary/bonus/taxes/contributions/debt, independent of the
    multi-million-dollar cash inflow landing that same month."""
    scenario = build_baseline_scenario()
    output = run_projection(scenario, terminal_age=60)

    event_1_month = scenario.household.liquidity_events[0].fixed_date
    from datetime import date

    period = output.period_at(date(event_1_month.year, event_1_month.month, 1))

    assert len(period.liquidity_events) == 1
    expected_implied_spending = (
        period.gross_income - period.estimated_taxes - period.contributions_401k - period.debt_service
    )
    assert period.implied_pre_retirement_spending == expected_implied_spending
