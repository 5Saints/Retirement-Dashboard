"""Tests for Section 7.5 withdrawal sequencing, guardrails, and Roth conversion
(Phase 5).
"""

from datetime import date
from decimal import Decimal

from fios_engine import scenario_library as lib
from fios_engine.models import Decision, DecisionType
from fios_engine.projection import run_projection
from fios_engine.seed import build_baseline_scenario

RETIREMENT_DATE = date(2032, 1, 1)


def test_default_withdrawal_order_is_cash_taxable_401k_roth():
    scenario = build_baseline_scenario()
    assert scenario.withdrawal_order == ("cash", "taxable", "401k", "roth")


# Both after the Jan-2032 retirement-linked liquidity event settles (so taxable's
# balance isn't swamped by that one-time proceeds injection) and before the $100k cash
# balance fully depletes under ~$25k/month spending (which happens within ~4 months).
STEADY_STATE_BEFORE = date(2032, 2, 1)
STEADY_STATE_AFTER = date(2032, 3, 1)


def test_sequential_order_does_not_touch_later_accounts_while_earlier_ones_suffice():
    scenario = build_baseline_scenario()
    output = run_projection(scenario, terminal_age=60, retirement_date=RETIREMENT_DATE)
    before = output.period_at(STEADY_STATE_BEFORE)
    after = output.period_at(STEADY_STATE_AFTER)

    # Cash alone comfortably covers one month's target this early in retirement, so
    # taxable/401k should be untouched by withdrawals that month (growth only).
    assert after.account_balances["cash"] < before.account_balances["cash"]
    taxable_growth_only = before.account_balances["taxable"] * (1 + Decimal("0.06") / 12)
    assert abs(after.account_balances["taxable"] - taxable_growth_only) < Decimal("0.01")


def test_custom_withdrawal_order_draws_taxable_before_cash():
    scenario = build_baseline_scenario()
    scenario.withdrawal_order = ("taxable", "cash", "401k", "roth")
    output = run_projection(scenario, terminal_age=60, retirement_date=RETIREMENT_DATE)
    before = output.period_at(STEADY_STATE_BEFORE)
    after = output.period_at(STEADY_STATE_AFTER)

    cash_growth_only = before.account_balances["cash"] * (1 + Decimal("0") / 12)
    assert abs(after.account_balances["cash"] - cash_growth_only) < Decimal("0.01")
    assert after.account_balances["taxable"] < before.account_balances["taxable"]


def test_proportional_strategy_leaves_more_in_cash_than_sequential():
    """Both baseline account balances dwarf one month's spending target, so a raw
    before/after balance delta on any single account is noisy (investment growth can
    outweigh a proportionally tiny draw). Comparing the two strategies side by side at
    the same date is the robust signal: sequential drains cash first and leaves
    taxable untouched that month, while proportional takes only a small weighted slice
    of cash and a corresponding slice of taxable too."""
    sequential = build_baseline_scenario()
    proportional = build_baseline_scenario()
    proportional.withdrawal_strategy = "proportional"

    sequential_output = run_projection(sequential, terminal_age=60, retirement_date=RETIREMENT_DATE)
    proportional_output = run_projection(proportional, terminal_age=60, retirement_date=RETIREMENT_DATE)

    sequential_period = sequential_output.period_at(STEADY_STATE_AFTER)
    proportional_period = proportional_output.period_at(STEADY_STATE_AFTER)

    assert proportional_period.account_balances["cash"] > sequential_period.account_balances["cash"]
    assert proportional_period.account_balances["taxable"] < sequential_period.account_balances["taxable"]
    assert proportional_period.actual_spending == Decimal("25000")


def test_roth_conversion_moves_money_and_taxes_the_funding_source():
    scenario = build_baseline_scenario()
    conversion_date = date(2032, 6, 1)
    scenario.household.decisions = [
        Decision(DecisionType.ROTH_CONVERSION, conversion_date, Decimal("50000"), funding_source="taxable")
    ]
    output = run_projection(scenario, terminal_age=60, retirement_date=RETIREMENT_DATE)

    without_conversion = run_projection(build_baseline_scenario(), terminal_age=60, retirement_date=RETIREMENT_DATE)
    at = output.period_at(conversion_date)
    baseline_at = without_conversion.period_at(conversion_date)

    assert at.account_balances["roth"] > Decimal("0")
    assert baseline_at.account_balances["401k"] - at.account_balances["401k"] > Decimal("49000")
    assert baseline_at.account_balances["taxable"] - at.account_balances["taxable"] > Decimal("12000")
    assert at.conversion_tax == Decimal("12500.00")


def test_roth_conversion_at_or_after_rmd_age_emits_a_warning():
    scenario = build_baseline_scenario()
    # current_age 53 in 2026; rmd_age defaults to 73 -> reached in 2046.
    late_conversion_date = date(2046, 1, 1)
    scenario.household.decisions = [
        Decision(DecisionType.ROTH_CONVERSION, late_conversion_date, Decimal("10000"), funding_source="taxable")
    ]
    output = run_projection(scenario, terminal_age=90, retirement_date=RETIREMENT_DATE)

    period = output.period_at(late_conversion_date)
    assert any("RMD" in w for w in period.warnings)


def test_roth_conversion_before_rmd_age_has_no_warning():
    scenario = build_baseline_scenario()
    scenario.household.decisions = [
        Decision(DecisionType.ROTH_CONVERSION, date(2032, 6, 1), Decimal("10000"), funding_source="taxable")
    ]
    output = run_projection(scenario, terminal_age=60, retirement_date=RETIREMENT_DATE)

    period = output.period_at(date(2032, 6, 1))
    assert not any("RMD" in w for w in period.warnings)


def test_spending_guardrails_scale_the_monthly_target():
    expectations = {
        "full_budget": Decimal("25000"),
        "discretionary_cuts": Decimal("18750.00"),
        "essential_only": Decimal("12500.00"),
    }
    for guardrail, expected in expectations.items():
        scenario = build_baseline_scenario()
        scenario.spending_guardrail = guardrail
        output = run_projection(scenario, terminal_age=60, retirement_date=RETIREMENT_DATE)
        actual = output.period_at(RETIREMENT_DATE).actual_spending
        assert actual == expected, f"{guardrail}: expected {expected}, got {actual}"


def test_real_estate_last_resort_is_off_by_default_even_under_depletion():
    scenario = build_baseline_scenario()
    for category in scenario.household.expense_categories:
        category.anchor_amount = category.anchor_amount * 50
    output = run_projection(scenario, terminal_age=60, retirement_date=RETIREMENT_DATE)

    depleted_period = next(p for p in output.periods if p.warnings)
    assert depleted_period.real_estate_value > Decimal("0")


def test_real_estate_last_resort_liquidates_when_enabled_and_needed():
    scenario = build_baseline_scenario()
    for category in scenario.household.expense_categories:
        category.anchor_amount = category.anchor_amount * 50
    scenario.allow_real_estate_liquidation_as_last_resort = True
    scenario.real_estate_last_resort_property = "Lake home"
    output = run_projection(scenario, terminal_age=60, retirement_date=RETIREMENT_DATE)

    without_last_resort = build_baseline_scenario()
    for category in without_last_resort.household.expense_categories:
        category.anchor_amount = category.anchor_amount * 50
    baseline_output = run_projection(without_last_resort, terminal_age=60, retirement_date=RETIREMENT_DATE)

    total_re_with = sum(p.real_estate_value for p in output.periods)
    total_re_without = sum(p.real_estate_value for p in baseline_output.periods)
    assert total_re_with < total_re_without


def test_roth_conversion_builder_does_not_mutate_parent():
    baseline = build_baseline_scenario()

    scenario = lib.roth_conversion(baseline, Decimal("40000"), date(2032, 1, 1))

    assert len(scenario.household.decisions) == 1
    assert scenario.household.decisions[0].decision_type is DecisionType.ROTH_CONVERSION
    assert baseline.household.decisions == []
