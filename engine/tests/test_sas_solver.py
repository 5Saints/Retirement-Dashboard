"""Tests for the Sustainable Annual Spending solver."""

from datetime import date
from decimal import Decimal

from fios_engine.sas_solver import _evaluate, solve_sas
from fios_engine.seed import build_baseline_scenario
from fios_engine.woa_solver import solve_woa


def test_sas_at_planned_2032_retirement_is_below_the_300k_anchor():
    scenario = build_baseline_scenario()

    result = solve_sas(scenario, date(2032, 1, 1))

    assert result.bounded is True
    assert Decimal("0") < result.sustainable_spending < Decimal("300000")


def test_sas_converges_within_tolerance_of_the_pass_fail_boundary():
    scenario = build_baseline_scenario()
    candidate = date(2032, 1, 1)
    tolerance = Decimal("100")

    result = solve_sas(scenario, candidate, tolerance=tolerance)

    just_above = result.sustainable_spending + tolerance * 2
    assert _evaluate(scenario, candidate, result.sustainable_spending).all_passed is True
    assert _evaluate(scenario, candidate, just_above).all_passed is False


def test_sas_at_woa_exceeds_the_300k_anchor():
    """Retiring at the solved WOA (later than 2032) leaves a shorter retirement
    horizon and more accumulation, so sustainable spending there should comfortably
    clear the $300,000 anchor -- consistent with WOA being defined as the date the
    anchor-based tests actually pass."""
    scenario = build_baseline_scenario()
    woa = solve_woa(scenario)

    result = solve_sas(scenario, woa.candidate_date)

    assert result.sustainable_spending > Decimal("300000")
