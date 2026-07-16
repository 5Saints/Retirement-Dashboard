"""Tests for Decision injection in the monthly projection loop (Section 11/28)."""

from datetime import date
from decimal import Decimal

from fios_engine.models import Decision, DecisionType
from fios_engine.projection import run_projection
from fios_engine.seed import build_baseline_scenario


def test_real_estate_purchase_debits_funding_source_and_credits_real_estate():
    purchase_date = date(2027, 6, 1)
    scenario = build_baseline_scenario()
    scenario.household.decisions = [
        Decision(
            DecisionType.REAL_ESTATE_PURCHASE,
            purchase_date,
            Decimal("200000"),
            funding_source="taxable",
            description="Ski condo",
        )
    ]

    with_decision = run_projection(scenario, terminal_age=60)
    without_decision = run_projection(build_baseline_scenario(), terminal_age=60)
    at = with_decision.period_at(purchase_date)
    baseline_at = without_decision.period_at(purchase_date)

    # The "additional property" bucket has zero appreciation (Section 4.8), so the
    # real-estate-value delta from the purchase alone is exact even within the same
    # month; the taxable-balance delta also picks up that month's investment return.
    assert at.real_estate_value - baseline_at.real_estate_value == Decimal("200000")
    assert baseline_at.account_balances["taxable"] - at.account_balances["taxable"] > Decimal("200000")


def test_real_estate_sale_liquidates_named_property_to_destination_account():
    scenario = build_baseline_scenario()
    sale_date = date(2040, 1, 1)
    scenario.household.decisions = [
        Decision(
            DecisionType.REAL_ESTATE_SALE,
            sale_date,
            Decimal("0"),
            funding_source="taxable",
            description="Lake home",
        )
    ]

    output = run_projection(scenario, terminal_age=70)
    before = output.period_at(date(2039, 12, 1))
    after = output.period_at(sale_date)

    taxable_gain = after.account_balances["taxable"] - before.account_balances["taxable"]
    re_drop = before.real_estate_value - after.real_estate_value

    # Both deltas reflect the same sale proceeds, but the credited account and the
    # zeroed property compound at different rates for the rest of that same month
    # (Section 4.6 taxable return vs. Section 4.8 real-estate appreciation), so they
    # match closely rather than exactly.
    assert taxable_gain > Decimal("1000000")
    assert re_drop > Decimal("1000000")
    assert abs(taxable_gain - re_drop) / re_drop < Decimal("0.01")


def test_spending_adjustment_increases_post_retirement_withdrawal():
    scenario = build_baseline_scenario()
    retirement_date = date(2032, 1, 1)
    scenario.household.decisions = [
        Decision(
            DecisionType.SPENDING_ADJUSTMENT,
            retirement_date,
            Decimal("24000"),
            recurring_effect=True,
        )
    ]

    baseline_output = run_projection(build_baseline_scenario(), terminal_age=60, retirement_date=retirement_date)
    adjusted_output = run_projection(scenario, terminal_age=60, retirement_date=retirement_date)

    baseline_spend = baseline_output.period_at(retirement_date).actual_spending
    adjusted_spend = adjusted_output.period_at(retirement_date).actual_spending

    assert adjusted_spend - baseline_spend == Decimal("2000")


def test_one_time_spending_adjustment_does_not_recur_the_following_year():
    scenario = build_baseline_scenario()
    retirement_date = date(2032, 1, 1)
    scenario.household.decisions = [
        Decision(
            DecisionType.SPENDING_ADJUSTMENT,
            retirement_date,
            Decimal("12000"),
            recurring_effect=False,
        )
    ]

    output = run_projection(scenario, terminal_age=60, retirement_date=retirement_date)
    same_year = output.period_at(date(2032, 6, 1))
    next_year = output.period_at(date(2033, 1, 1))

    baseline_output = run_projection(build_baseline_scenario(), terminal_age=60, retirement_date=retirement_date)
    baseline_same_year = baseline_output.period_at(date(2032, 6, 1))
    baseline_next_year = baseline_output.period_at(date(2033, 1, 1))

    assert same_year.actual_spending - baseline_same_year.actual_spending == Decimal("1000")
    assert next_year.actual_spending - baseline_next_year.actual_spending == Decimal("0")
