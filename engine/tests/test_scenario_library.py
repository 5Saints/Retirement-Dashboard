"""Spot checks for the Section 8.1/28 built-in scenario builders."""

from datetime import date
from decimal import Decimal

from fios_engine import scenario_library as lib
from fios_engine.models import Status
from fios_engine.projection import run_projection
from fios_engine.seed import build_baseline_scenario


def test_conservative_and_optimistic_returns_bracket_expected():
    baseline = build_baseline_scenario()

    conservative = lib.conservative_returns(baseline)
    expected = lib.expected_returns(baseline)
    optimistic = lib.optimistic_returns(baseline)

    assert conservative.household.accounts["taxable"].annual_return.value == Decimal("0.04")
    assert expected.household.accounts["taxable"].annual_return.value == Decimal("0.06")
    assert optimistic.household.accounts["taxable"].annual_return.value == Decimal("0.08")
    # cash is never stressed -- it earns 0% under every return scenario.
    assert conservative.household.accounts["cash"].annual_return.value == Decimal("0")


def test_higher_tax_on_company_payouts_increases_both_events():
    baseline = build_baseline_scenario()

    scenario = lib.higher_tax_on_company_payouts(baseline)

    for original, changed in zip(baseline.household.liquidity_events, scenario.household.liquidity_events):
        assert changed.tax_rate.value == original.tax_rate.value + lib.HIGHER_TAX_DELTA
        assert changed.tax_rate.status is Status.ASSUMPTION


def test_lower_company_payout_reduces_the_2030_anchor_only():
    baseline = build_baseline_scenario()

    scenario = lib.lower_company_payout(baseline)

    anchors = scenario.household.equity_positions[0].anchors
    confirmed = [a for a in anchors if a.status is Status.CONFIRMED]
    assumption = [a for a in anchors if a.status is Status.ASSUMPTION]
    assert confirmed[0].price == Decimal("21589.92")
    assert assumption[0].price == lib.LOWER_PAYOUT_ANCHOR_PRICE
    assert assumption[0].price < Decimal("70000")


def test_retire_at_age_changes_only_planned_retirement_age():
    baseline = build_baseline_scenario()

    scenario = lib.retire_at_age(baseline, 57)

    assert scenario.household.planned_retirement_age == 57
    assert scenario.household.retirement_date.year == 2030
    assert baseline.household.planned_retirement_age == 59


def test_reduce_discretionary_spending_leaves_essential_categories_untouched():
    baseline = build_baseline_scenario()

    scenario = lib.reduce_discretionary_spending(baseline, Decimal("0.20"))

    for original, changed in zip(baseline.household.expense_categories, scenario.household.expense_categories):
        if original.essential:
            assert changed.anchor_amount == original.anchor_amount
        else:
            assert changed.anchor_amount == original.anchor_amount * Decimal("0.80")


def test_purchase_additional_real_estate_and_lake_home_sale_apply_via_decisions():
    baseline = build_baseline_scenario()

    purchase_scenario = lib.purchase_additional_real_estate(
        baseline, Decimal("300000"), date(2028, 1, 1), funding_source="taxable"
    )
    sale_scenario = lib.emergency_lake_home_sale(baseline, date(2035, 1, 1))

    assert len(purchase_scenario.household.decisions) == 1
    assert len(sale_scenario.household.decisions) == 1
    assert baseline.household.decisions == []

    # Both should run cleanly through the projection engine.
    run_projection(purchase_scenario, terminal_age=60)
    run_projection(sale_scenario, terminal_age=60)


def test_market_decline_shocks_price_path_only_and_flags_the_gap():
    baseline = build_baseline_scenario()

    scenario = lib.market_decline(baseline)

    anchors = scenario.household.equity_positions[0].anchors
    assert len(anchors) == len(baseline.household.equity_positions[0].anchors) + 1
    assert len(scenario.changes) == 1
    assert "equity price path only" in scenario.changes[0].source
