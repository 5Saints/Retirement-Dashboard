"""WOA candidate-date solver (PRD Section 6.3, CR-007).

Solver sequence per Section 6.3:

    1. Coarse annual scan using deterministic tests only, to bracket the earliest
       passing year.
    2. Monthly bisection within the bracket to find the earliest deterministic pass.
    3. Monte Carlo verification at that single candidate, if the stress test is enabled.
    4. On verification failure, step forward monthly, re-verifying, until pass.

Bisection is valid because monotonicity is asserted as a model invariant (Section 6.3):
if all enabled tests pass at candidate date D, they pass at every later date. See
tests/test_monotonicity.py for the property-based test the PRD requires against that
invariant.

Steps 3-4 (Phase 4) run Monte Carlo only once the earliest deterministic-passing
candidate is found: running 10,000 simulations at every coarse-scan/bisection candidate
would defeat Section 6.3's own performance target, so the (cheap) deterministic suite
does all of the bracketing and only the final candidate -- and any monthly step-forward
retries -- pay the Monte Carlo cost. `Scenario.monte_carlo_enabled=False` skips steps
3-4 entirely for callers that want a fast deterministic-only solve (most tests), in
which case `monte_carlo_verified` stays `False` and `status` stays `Status.PLACEHOLDER`,
same as Phase 2 -- an explicit, visible flag rather than a silent assumption that
verification happened.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .models import Scenario, Status
from .monte_carlo import DEFAULT_SEED, DEFAULT_SIMULATIONS, MonteCarloResult, run_monte_carlo
from .projection import add_months, run_projection
from .retirement_tests import RetirementTestSuite, evaluate_all_tests
from .spending import build_schedule


@dataclass(frozen=True)
class WOACandidate:
    candidate_date: date
    tests: RetirementTestSuite

    @property
    def passed(self) -> bool:
        return self.tests.all_passed


@dataclass(frozen=True)
class WOAResult:
    achievable: bool
    candidate_date: date | None
    tests: RetirementTestSuite | None
    monte_carlo_verified: bool
    trace: list[WOACandidate]
    monte_carlo_result: MonteCarloResult | None = None
    not_achievable_reason: str | None = None
    status: Status = Status.CONFIRMED


def _month_diff(a: date, b: date) -> int:
    return (b.year - a.year) * 12 + (b.month - a.month)


def _last_search_date(scenario: Scenario) -> date:
    household = scenario.household
    months_to_terminal = (scenario.terminal_age - household.current_age) * 12
    months_to_boundary = max(months_to_terminal - scenario.cash_reserve_months, 0)
    return add_months(household.current_date, months_to_boundary)


def _evaluate_candidate(scenario: Scenario, candidate_date: date) -> WOACandidate:
    projection = run_projection(
        scenario, terminal_age=scenario.terminal_age, retirement_date=candidate_date
    )
    schedule = build_schedule(
        scenario.household.expense_categories, candidate_date.year, scenario.retirement_inflation_rate
    )
    tests = evaluate_all_tests(
        scenario, projection, candidate_date, scenario.terminal_age, schedule.first_year_total
    )
    return WOACandidate(candidate_date, tests)


def solve_woa(
    scenario: Scenario,
    num_mc_simulations: int = DEFAULT_SIMULATIONS,
    mc_seed: int = DEFAULT_SEED,
) -> WOAResult:
    household = scenario.household
    earliest_candidate = household.current_date
    last_candidate = _last_search_date(scenario)

    trace: list[WOACandidate] = []

    # 1. Coarse annual scan.
    coarse_dates = []
    current = earliest_candidate
    while current < last_candidate:
        coarse_dates.append(current)
        current = add_months(current, 12)
    coarse_dates.append(last_candidate)

    lo: date | None = None
    hi: date | None = None
    for candidate_date in coarse_dates:
        result = _evaluate_candidate(scenario, candidate_date)
        trace.append(result)
        if result.passed:
            hi = candidate_date
            break
        lo = candidate_date

    if hi is None:
        last_result = trace[-1]
        failure = last_result.tests.first_failure()
        reason = (
            f"no candidate date up to {last_candidate} passes every enabled test; "
            f"earliest failure at {last_result.candidate_date}: "
            f"{failure.name} ({failure.detail})"
            if failure is not None
            else f"no candidate date up to {last_candidate} passes every enabled test"
        )
        return WOAResult(
            achievable=False,
            candidate_date=None,
            tests=None,
            monte_carlo_verified=False,
            trace=trace,
            not_achievable_reason=reason,
        )

    # 2. Monthly bisection between the last failing coarse candidate (if any) and the
    # first passing one, relying on the monotonicity invariant.
    if lo is not None:
        lo_index = 0
        hi_index = _month_diff(lo, hi)
        while hi_index - lo_index > 1:
            mid_index = (lo_index + hi_index) // 2
            mid_date = add_months(lo, mid_index)
            result = _evaluate_candidate(scenario, mid_date)
            trace.append(result)
            if result.passed:
                hi_index = mid_index
            else:
                lo_index = mid_index
        earliest_passing_date = add_months(lo, hi_index)
    else:
        earliest_passing_date = hi

    final = next(
        (c for c in reversed(trace) if c.candidate_date == earliest_passing_date and c.passed),
        None,
    )
    if final is None:
        final = _evaluate_candidate(scenario, earliest_passing_date)
        trace.append(final)

    if not scenario.monte_carlo_enabled:
        return WOAResult(
            achievable=True,
            candidate_date=final.candidate_date,
            tests=final.tests,
            monte_carlo_verified=False,
            trace=trace,
            status=Status.PLACEHOLDER,
        )

    # 3-4. Monte Carlo verification at the earliest deterministic pass; on failure,
    # step forward monthly (re-verifying deterministic tests too, per the monotonicity
    # invariant) until Monte Carlo passes or the search boundary is reached.
    candidate = final
    while True:
        mc_result = run_monte_carlo(
            scenario,
            candidate.candidate_date,
            terminal_age=scenario.terminal_age,
            num_simulations=num_mc_simulations,
            seed=mc_seed,
        )
        if mc_result.success_probability >= float(scenario.success_threshold):
            return WOAResult(
                achievable=True,
                candidate_date=candidate.candidate_date,
                tests=candidate.tests,
                monte_carlo_verified=True,
                trace=trace,
                monte_carlo_result=mc_result,
            )

        next_date = add_months(candidate.candidate_date, 1)
        if next_date > last_candidate:
            return WOAResult(
                achievable=False,
                candidate_date=None,
                tests=None,
                monte_carlo_verified=False,
                trace=trace,
                monte_carlo_result=mc_result,
                not_achievable_reason=(
                    f"deterministic tests pass from {final.candidate_date}, but Monte Carlo "
                    f"success probability ({mc_result.success_probability:.1%}) never reaches "
                    f"the {float(scenario.success_threshold):.1%} threshold by {last_candidate}"
                ),
            )
        candidate = _evaluate_candidate(scenario, next_date)
        trace.append(candidate)
        if not candidate.passed:
            failure = candidate.tests.first_failure()
            return WOAResult(
                achievable=False,
                candidate_date=None,
                tests=None,
                monte_carlo_verified=False,
                trace=trace,
                monte_carlo_result=mc_result,
                not_achievable_reason=(
                    f"deterministic test {failure.name} unexpectedly failed at {next_date} while "
                    "stepping forward for Monte Carlo verification -- monotonicity invariant "
                    "violated (see tests/test_monotonicity.py)"
                    if failure is not None
                    else f"deterministic tests unexpectedly failed at {next_date}"
                ),
            )
