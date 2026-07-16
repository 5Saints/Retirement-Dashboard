"""Property-based test for the Section 6.3 monotonicity invariant: "if all enabled
tests pass at candidate date D, they pass at every later date." The WOA solver's
bisection step (woa_solver.py) is only correct if this holds; per Section 6.3, "if a
future feature breaks monotonicity, that test fails and the solver strategy must be
revisited by change request" -- this is that test.
"""

from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from fios_engine.projection import add_months, run_projection
from fios_engine.retirement_tests import evaluate_deterministic_tests
from fios_engine.seed import build_baseline_scenario
from fios_engine.spending import build_schedule


def _passes_deterministic(scenario, candidate_date) -> bool:
    projection = run_projection(
        scenario, terminal_age=scenario.terminal_age, retirement_date=candidate_date
    )
    schedule = build_schedule(
        scenario.household.expense_categories, candidate_date.year, scenario.retirement_inflation_rate
    )
    suite = evaluate_deterministic_tests(
        scenario, projection, candidate_date, schedule.first_year_total
    )
    return suite.all_passed


@settings(max_examples=25, deadline=None)
@given(
    inflation_rate=st.sampled_from([Decimal("0.00"), Decimal("0.02"), Decimal("0.03"), Decimal("0.05")]),
    start_month_offset=st.integers(min_value=0, max_value=420),
    later_month_delta=st.integers(min_value=1, max_value=36),
)
def test_deterministic_tests_are_monotonic_in_candidate_date(
    inflation_rate, start_month_offset, later_month_delta
):
    scenario = build_baseline_scenario()
    scenario.retirement_inflation_rate = inflation_rate

    earlier_date = add_months(scenario.household.current_date, start_month_offset)
    later_date = add_months(earlier_date, later_month_delta)

    if _passes_deterministic(scenario, earlier_date):
        assert _passes_deterministic(scenario, later_date)
