"""Golden-file tests reproducing the exact PRD Section 19 acceptance numbers."""

from decimal import Decimal

from fios_engine.equity import concentration_risk_index, run_share_ledger
from fios_engine.metrics import investable_assets, net_worth, total_assets
from fios_engine.money import to_cents, to_dollars
from fios_engine.projection import annual_amount_in_year, run_projection
from fios_engine.seed import build_baseline_household, build_baseline_scenario


def test_baseline_balance_sheet():
    household = build_baseline_household()
    equity_value = household.equity_positions[0].value(household.current_date)
    account_balances = {name: acc.opening_balance for name, acc in household.accounts.items()}
    real_estate_value = sum((r.value for r in household.real_estate), Decimal("0"))

    assets = total_assets(account_balances, equity_value, real_estate_value)
    liabilities = sum((l.opening_balance for l in household.liabilities.values()), Decimal("0"))
    nw = net_worth(assets, liabilities)

    assert to_cents(equity_value) == Decimal("3586560.69")
    assert to_cents(assets) == Decimal("6861560.69")
    assert liabilities == Decimal("100000")
    assert to_cents(nw) == Decimal("6761560.69")


def test_salary_and_total_compensation_2032():
    household = build_baseline_household()
    salary_stream = next(s for s in household.income_streams if s.name == "Salary")
    bonus_stream = next(s for s in household.income_streams if s.name == "Annual bonus")

    salary_2032 = annual_amount_in_year(salary_stream, household.current_date.year, 2032)
    total_comp_2032 = salary_2032 + annual_amount_in_year(bonus_stream, household.current_date.year, 2032)

    assert to_dollars(salary_2032) == Decimal("351363")
    assert to_dollars(total_comp_2032) == Decimal("451363")


def test_liquidity_event_1_derivation():
    household = build_baseline_household()
    equity_position = household.equity_positions[0]
    event_1 = household.liquidity_events[0]

    result = event_1.derive(household.retirement_date)

    assert result.gross == Decimal("2400000.28")
    assert result.tax == Decimal("720000.08")
    assert result.net == Decimal("1680000.20")
    assert result.real_estate_allocation == Decimal("500000")
    assert result.invested == Decimal("1180000.20")


def test_liquidity_event_2_derivation_baseline():
    household = build_baseline_household()
    event_2 = household.liquidity_events[1]

    result = event_2.derive(household.retirement_date)

    assert result.gross == Decimal("3847130.00")
    assert result.tax == Decimal("1154139.00")
    assert result.invested == Decimal("2692991.00")


def test_share_ledger_after_both_events():
    household = build_baseline_household()
    equity_position = household.equity_positions[0]

    steps = run_share_ledger(equity_position, household.liquidity_events, household.retirement_date)

    assert steps[0].shares_remaining_after == Decimal("54.959")
    assert steps[1].shares_remaining_after == Decimal("0")

    equity_value_after = steps[1].shares_remaining_after * equity_position.resolve_price(
        household.retirement_date
    )
    assert concentration_risk_index(equity_value_after, Decimal("1000000")) == Decimal("0")


def test_2028_candidate_prices_from_2028_anchor():
    """A candidate retirement date of 2028 prices the retirement-linked liquidation at
    the price anchor applicable to 2028. With only 2026 and 2030 anchors populated,
    step interpolation resolves 2028 to the 2026 anchor -- exercising the required
    mechanism ahead of the 2027-2029 anchors being supplied (CL-4)."""
    household = build_baseline_household()
    equity_position = household.equity_positions[0]
    from datetime import date

    candidate_retirement_date = date(2028, 1, 1)
    event_2 = household.liquidity_events[1]

    result = event_2.derive(candidate_retirement_date)

    expected_price = equity_position.resolve_price(candidate_retirement_date)
    assert expected_price == Decimal("21589.92")
    assert result.gross == to_cents(Decimal("54.959") * expected_price)


def test_retirement_spending_anchor_values():
    from fios_engine.spending import first_year_spending

    inflation = Decimal("0.03")
    assert to_dollars(first_year_spending(2031, inflation)) == Decimal("291262")
    assert to_dollars(first_year_spending(2032, inflation)) == Decimal("300000")
    assert to_dollars(first_year_spending(2033, inflation)) == Decimal("309000")


def test_liabilities_zero_at_retirement_date():
    scenario = build_baseline_scenario()
    output = run_projection(scenario, terminal_age=60)
    retirement_period = output.period_at(scenario.household.retirement_date)

    assert to_cents(retirement_period.mortgage_balance) == Decimal("0.00")
