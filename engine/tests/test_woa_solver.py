"""Tests for the Section 6.3 WOA solver."""

from datetime import date

from fios_engine.models import Status
from fios_engine.projection import add_months
from fios_engine.seed import build_baseline_scenario
from fios_engine.woa_solver import _evaluate_candidate, solve_woa


def test_baseline_woa_is_achievable_and_later_than_the_300k_anchor_supports():
    """Since the $300,000 anchor isn't sustainable at the planned 2032 retirement
    (see test_retirement_tests.py), the solved WOA must land later than 2032. Monte
    Carlo disabled here -- this is testing the deterministic bisection, not Phase 4."""
    scenario = build_baseline_scenario()
    scenario.monte_carlo_enabled = False

    result = solve_woa(scenario)

    assert result.achievable is True
    assert result.candidate_date > date(2032, 1, 1)
    assert result.tests is not None
    assert result.tests.all_passed is True


def test_deterministic_candidate_is_the_earliest_passing_month():
    """Bisection must converge to the earliest passing month: one month earlier must
    fail, per the Section 6.3 monotonicity invariant. Monte Carlo disabled to isolate
    the deterministic bisection step (steps 1-2) from the Monte Carlo step-forward
    (steps 3-4, covered separately below)."""
    scenario = build_baseline_scenario()
    scenario.monte_carlo_enabled = False

    result = solve_woa(scenario)
    one_month_earlier = add_months(result.candidate_date, -1)

    earlier_candidate = _evaluate_candidate(scenario, one_month_earlier)

    assert earlier_candidate.passed is False


def test_monte_carlo_disabled_reports_unverified_placeholder():
    """`monte_carlo_enabled=False` must produce the same explicit, visible
    not-verified flag Phase 2 used before Monte Carlo existed -- never silently
    reported as verified."""
    scenario = build_baseline_scenario()
    scenario.monte_carlo_enabled = False

    result = solve_woa(scenario)

    assert result.monte_carlo_verified is False
    assert result.monte_carlo_result is None
    assert result.status is Status.PLACEHOLDER


def test_monte_carlo_verification_moves_the_candidate_later_and_meets_threshold():
    """Section 6.3 steps 3-4: Monte Carlo verification at the earliest deterministic
    pass, stepping forward monthly on failure. The deterministic-only candidate (see
    test_deterministic_candidate_is_the_earliest_passing_month) has a Monte Carlo
    success probability below the 90% default threshold, so the MC-verified WOA must
    land later, and its success probability must clear the threshold."""
    scenario = build_baseline_scenario()
    scenario.monte_carlo_enabled = False
    deterministic_only = solve_woa(scenario)

    scenario.monte_carlo_enabled = True
    result = solve_woa(scenario)

    assert result.achievable is True
    assert result.monte_carlo_verified is True
    assert result.status is Status.CONFIRMED
    assert result.monte_carlo_result is not None
    assert result.monte_carlo_result.success_probability >= float(scenario.success_threshold)
    assert result.candidate_date >= deterministic_only.candidate_date


def test_woa_not_achievable_when_terminal_age_is_too_close():
    """A household given essentially no time before its own terminal age can't pass
    any deterministic test; the solver must return Not Achievable with a reason rather
    than scanning indefinitely or raising. Fails during the coarse scan, before any
    Monte Carlo run would even be attempted."""
    scenario = build_baseline_scenario()
    scenario.terminal_age = scenario.household.current_age + 1

    result = solve_woa(scenario)

    assert result.achievable is False
    assert result.candidate_date is None
    assert result.not_achievable_reason is not None
