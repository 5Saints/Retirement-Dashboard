"""Unit tests for the Section 6.1 required retirement tests."""

from datetime import date
from decimal import Decimal

from fios_engine.projection import run_projection
from fios_engine.retirement_tests import (
    concentration_test,
    essential_fraction,
    evaluate_all_tests,
    liquidity_test,
    longevity_test,
    spending_test,
    tax_test,
)
from fios_engine.seed import build_baseline_scenario
from fios_engine.spending import build_schedule


def test_essential_fraction_is_half_for_baseline_categories():
    scenario = build_baseline_scenario()
    assert essential_fraction(scenario.household.expense_categories) == Decimal("0.5")


def test_concentration_fails_when_retiring_before_the_fixed_liquidity_event():
    """Event 1 is fixed at 2026-09-30 (CL-1); a candidate retirement date of 2026-01-01
    triggers only the retirement-linked Event 2 by then, leaving Event 1's shares
    (111.163) unliquidated -- concentration must fail, per Section 6.1's requirement
    that the test "remains active to flag scenarios that override liquidation" in a way
    that leaves equity exposure at retirement."""
    scenario = build_baseline_scenario()
    candidate = date(2026, 1, 1)
    projection = run_projection(scenario, terminal_age=scenario.terminal_age, retirement_date=candidate)

    outcome = concentration_test(scenario, projection, candidate)

    assert outcome.passed is False


def test_concentration_passes_once_both_events_have_occurred():
    scenario = build_baseline_scenario()
    candidate = date(2032, 1, 1)
    projection = run_projection(scenario, terminal_age=scenario.terminal_age, retirement_date=candidate)

    outcome = concentration_test(scenario, projection, candidate)

    assert outcome.passed is True


def test_longevity_and_spending_fail_at_the_300k_anchor_over_a_36_year_horizon():
    """At the household's own planned retirement age (59, 2032) the $300,000 real
    spending anchor is not sustainable through the Section 6.2 terminal age (95): the
    ~5% initial withdrawal rate against a ~$6.06M investable base outruns a 6% nominal
    return net of 3% spending growth well before age 95. This is the whole reason a WOA
    solver is useful -- it demonstrates the solver is not vacuously passing everything.
    """
    scenario = build_baseline_scenario()
    candidate = date(2032, 1, 1)
    projection = run_projection(scenario, terminal_age=scenario.terminal_age, retirement_date=candidate)

    assert longevity_test(projection).passed is False
    assert spending_test(projection).passed is False


def test_tax_test_always_passes():
    assert tax_test().passed is True


def test_liquidity_test_reserve_matches_essential_half_of_total_at_two_year_reserve():
    scenario = build_baseline_scenario()
    candidate = date(2032, 1, 1)
    projection = run_projection(scenario, terminal_age=scenario.terminal_age, retirement_date=candidate)
    schedule = build_schedule(candidate.year, scenario.retirement_inflation_rate)

    outcome = liquidity_test(scenario, projection, candidate, schedule.first_year_total)

    # essential_fraction == 0.5 and cash_reserve_months == 24 means the required
    # reserve collapses to exactly one year of the *full* (not just essential) target.
    essential_monthly = schedule.first_year_total * Decimal("0.5") / 12
    expected_required = essential_monthly * scenario.cash_reserve_months
    assert expected_required == schedule.first_year_total
    assert outcome.passed is True


def test_evaluate_all_tests_includes_stress_as_placeholder():
    scenario = build_baseline_scenario()
    candidate = date(2032, 1, 1)
    projection = run_projection(scenario, terminal_age=scenario.terminal_age, retirement_date=candidate)
    schedule = build_schedule(candidate.year, scenario.retirement_inflation_rate)

    suite = evaluate_all_tests(
        scenario, projection, candidate, scenario.terminal_age, schedule.first_year_total
    )

    names = [o.name for o in suite.outcomes]
    assert names == [
        "liquidity",
        "longevity",
        "spending",
        "legacy",
        "concentration",
        "tax",
        "stress",
    ]
    assert suite.all_passed is False
    assert suite.first_failure().name == "longevity"
