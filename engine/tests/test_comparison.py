"""Tests for scenario/decision comparison (Section 8.2 Decision Output)."""

from datetime import date

from fios_engine import scenario_library as lib
from fios_engine.comparison import compare_scenarios, what_changed
from fios_engine.models import Status
from fios_engine.sas_solver import solve_sas
from fios_engine.seed import build_baseline_scenario


def test_comparing_a_scenario_against_itself_is_a_no_op():
    baseline = build_baseline_scenario()
    identical = lib.expected_returns(baseline)

    comparison = compare_scenarios(baseline, identical)

    assert comparison.woa_impact_months == 0
    assert comparison.sas_impact_dollars == 0
    assert comparison.tax_impact == 0


def test_conservative_returns_pushes_woa_later():
    """Section 8.2's "WOA impact" comparison re-solves WOA for each scenario, so a
    worse return assumption should push the achievable Work-Optional Age later."""
    baseline = build_baseline_scenario()
    conservative = lib.conservative_returns(baseline)

    comparison = compare_scenarios(baseline, conservative)

    assert comparison.woa_impact_months is not None
    assert comparison.woa_impact_months > 0


def test_conservative_returns_lowers_sas_at_a_fixed_retirement_date():
    """Isolating the return assumption from the retirement-date effect: at the SAME
    candidate date, worse returns must mean less sustainable spending. (Comparing SAS
    at each scenario's own solved WOA, as `compare_scenarios` does by default, can move
    in either direction, since a later WOA also means fewer drawdown years -- that
    effect is covered by test_conservative_returns_pushes_woa_later above.)"""
    baseline = build_baseline_scenario()
    conservative = lib.conservative_returns(baseline)
    candidate = date(2032, 1, 1)

    baseline_sas = solve_sas(baseline, candidate).sustainable_spending
    conservative_sas = solve_sas(conservative, candidate).sustainable_spending

    assert conservative_sas < baseline_sas


def test_retiring_early_as_a_fixed_decision_lowers_sas_and_moves_woa_earlier():
    """Retirement-timing decisions must be evaluated at their own fixed date, not
    re-solved -- otherwise the comparison is a no-op (see comparison.snapshot's
    docstring and the bug this guards against)."""
    baseline = build_baseline_scenario()
    retire_early = lib.retire_at_age(baseline, 57)

    comparison = compare_scenarios(
        baseline, retire_early, alternative_retirement_date=retire_early.household.retirement_date
    )

    assert comparison.alternative.evaluated_at == retire_early.household.retirement_date
    assert comparison.woa_impact_months is not None
    assert comparison.woa_impact_months < 0
    assert comparison.sas_impact_dollars < 0


def test_success_probability_is_explicitly_unavailable():
    baseline = build_baseline_scenario()
    conservative = lib.conservative_returns(baseline)

    comparison = compare_scenarios(baseline, conservative)

    assert comparison.success_probability_before is None
    assert comparison.success_probability_after is None
    assert comparison.status is Status.PLACEHOLDER


def test_what_changed_reports_the_recorded_assumption_edit():
    baseline = build_baseline_scenario()
    higher_tax = lib.higher_tax_on_company_payouts(baseline)

    comparison = compare_scenarios(baseline, higher_tax)
    summary = what_changed(comparison, higher_tax)

    assert any("tax_rate" in line for line in summary)
