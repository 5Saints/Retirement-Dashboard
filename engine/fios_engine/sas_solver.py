"""Sustainable Annual Spending solver (PRD Section 5: "Maximum first-year retirement
spending supported under selected constraints... Solved iteratively; nominal dollars in
retirement year").

SAS varies the overall first-year spending level away from the Section 4.9 $300,000-
anchor target while holding the essential/discretionary category split fixed (the same
proportional-scaling rule Section 4.9 uses for retirement-date changes), then bisects
for the maximum level at which the Section 6.1 deterministic tests still pass at a
given retirement date. Monotonicity is assumed in the same direction as the WOA solver:
lower spending is only easier to sustain, never harder.

This module deliberately checks only the deterministic test suite (Section 6.1) minus
the stress proxy -- Section 5's SAS definition does not reference a stress/Monte Carlo
condition the way the WOA definition does (Section 6.1's stress test is a WOA-suite
member) -- so no stress run doubles the cost of every bisection step.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .models import Scenario
from .projection import run_projection
from .retirement_tests import RetirementTestSuite, evaluate_deterministic_tests
from .spending import SpendingSchedule, first_year_spending

DEFAULT_TOLERANCE = Decimal("100")
MAX_DOUBLINGS = 40


@dataclass(frozen=True)
class SASResult:
    sustainable_spending: Decimal
    bounded: bool
    trace: list[tuple[Decimal, RetirementTestSuite]]


def _evaluate(scenario: Scenario, retirement_date: date, candidate_total: Decimal) -> RetirementTestSuite:
    schedule = SpendingSchedule(
        retirement_year=retirement_date.year,
        first_year_total=candidate_total,
        inflation_rate=scenario.retirement_inflation_rate,
    )
    projection = run_projection(
        scenario,
        terminal_age=scenario.terminal_age,
        retirement_date=retirement_date,
        spending_schedule=schedule,
    )
    return evaluate_deterministic_tests(scenario, projection, retirement_date, candidate_total)


def solve_sas(
    scenario: Scenario,
    retirement_date: date,
    tolerance: Decimal = DEFAULT_TOLERANCE,
) -> SASResult:
    trace: list[tuple[Decimal, RetirementTestSuite]] = []

    lo = Decimal("0")
    hi = max(
        first_year_spending(retirement_date.year, scenario.retirement_inflation_rate) * 4,
        Decimal("1000000"),
    )

    hi_tests = _evaluate(scenario, retirement_date, hi)
    trace.append((hi, hi_tests))
    doublings = 0
    while hi_tests.all_passed and doublings < MAX_DOUBLINGS:
        hi *= 2
        hi_tests = _evaluate(scenario, retirement_date, hi)
        trace.append((hi, hi_tests))
        doublings += 1

    if hi_tests.all_passed:
        return SASResult(sustainable_spending=hi, bounded=False, trace=trace)

    while hi - lo > tolerance:
        mid = (lo + hi) / 2
        mid_tests = _evaluate(scenario, retirement_date, mid)
        trace.append((mid, mid_tests))
        if mid_tests.all_passed:
            lo = mid
        else:
            hi = mid

    return SASResult(sustainable_spending=lo, bounded=True, trace=trace)
