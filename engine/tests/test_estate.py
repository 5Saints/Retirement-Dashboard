"""Tests for Legacy Value / estate projections (Section 5; Phase 7)."""

from datetime import date

from fios_engine.estate import LEGACY_REPORT_AGES, age_date, legacy_values, net_worth_at_age
from fios_engine.projection import run_projection
from fios_engine.seed import build_baseline_scenario


def test_age_date_matches_household_age_arithmetic():
    scenario = build_baseline_scenario()
    household = scenario.household

    result = age_date(scenario, household.current_age + 10)

    assert result.year == household.current_date.year + 10
    assert result.month == household.current_date.month
    assert result.day == household.current_date.day


def test_net_worth_at_age_matches_period_result_net_worth():
    scenario = build_baseline_scenario()
    projection = run_projection(scenario, terminal_age=scenario.terminal_age)

    target = age_date(scenario, 75)
    expected = next(p for p in projection.periods if p.period_date >= target)

    assert net_worth_at_age(projection, scenario, 75) == expected.net_worth


def test_net_worth_at_age_is_none_past_projection_horizon():
    scenario = build_baseline_scenario()
    projection = run_projection(scenario, terminal_age=70)

    assert net_worth_at_age(projection, scenario, 95) is None


def test_legacy_values_covers_default_report_ages():
    scenario = build_baseline_scenario()

    values = legacy_values(scenario)

    assert set(values.keys()) == set(LEGACY_REPORT_AGES)
    assert all(v is not None for v in values.values())


def test_legacy_values_grows_horizon_to_cover_requested_ages():
    """A scenario with a terminal_age below the oldest requested legacy age must still
    get a value for that age -- legacy_values extends the internal projection horizon
    rather than truncating it (Section 5 doesn't gate legacy reporting on terminal_age)."""
    scenario = build_baseline_scenario()
    scenario.terminal_age = 80

    values = legacy_values(scenario, ages=(75, 85, 95))

    assert values[95] is not None


def test_legacy_values_at_a_fixed_retirement_date_matches_net_worth_at_age():
    scenario = build_baseline_scenario()
    fixed_date = date(2033, 1, 1)

    values = legacy_values(scenario, retirement_date=fixed_date)
    projection = run_projection(scenario, terminal_age=scenario.terminal_age, retirement_date=fixed_date)

    assert values[75] == net_worth_at_age(projection, scenario, 75)
