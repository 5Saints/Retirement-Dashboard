"""Tests for the Section 6.3 WOA solver."""

from datetime import date

from fios_engine.models import Status
from fios_engine.projection import add_months
from fios_engine.seed import build_baseline_scenario
from fios_engine.woa_solver import _evaluate_candidate, solve_woa


def test_baseline_woa_is_achievable_and_later_than_the_300k_anchor_supports():
    """Since the $300,000 anchor isn't sustainable at the planned 2032 retirement
    (see test_retirement_tests.py), the solved WOA must land later than 2032."""
    scenario = build_baseline_scenario()

    result = solve_woa(scenario)

    assert result.achievable is True
    assert result.candidate_date > date(2032, 1, 1)
    assert result.tests is not None
    assert result.tests.all_passed is True


def test_woa_candidate_is_the_earliest_passing_month():
    """Bisection must converge to the earliest passing month: one month earlier must
    fail, per the Section 6.3 monotonicity invariant."""
    scenario = build_baseline_scenario()

    result = solve_woa(scenario)
    one_month_earlier = add_months(result.candidate_date, -1)

    earlier_candidate = _evaluate_candidate(scenario, one_month_earlier)

    assert earlier_candidate.passed is False


def test_monte_carlo_verification_is_flagged_not_done():
    """Phase 4 (Monte Carlo) doesn't exist yet; the solver must say so explicitly
    rather than silently reporting a verified result."""
    scenario = build_baseline_scenario()

    result = solve_woa(scenario)

    assert result.monte_carlo_verified is False
    assert result.status is Status.PLACEHOLDER


def test_woa_not_achievable_when_terminal_age_is_too_close():
    """A household given essentially no time before its own terminal age can't pass
    any deterministic test; the solver must return Not Achievable with a reason rather
    than scanning indefinitely or raising."""
    scenario = build_baseline_scenario()
    scenario.terminal_age = scenario.household.current_age + 1

    result = solve_woa(scenario)

    assert result.achievable is False
    assert result.candidate_date is None
    assert result.not_achievable_reason is not None
