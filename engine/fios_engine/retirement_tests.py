"""Required retirement tests (PRD Section 6.1), evaluated against a single candidate
projection run.

Phase 2 implements the deterministic tests directly. Two tests are structurally
trivial by the baseline household's own construction, per the PRD's own notes, not by
omission here:

- Concentration: CR-005's retirement-linked liquidation (`DateMode.RETIREMENT_LINKED`
  on the second liquidity event) fully unwinds the employer-equity position exactly at
  whatever candidate retirement date is evaluated, so the test passes by construction
  for the baseline (Section 6.1: "the baseline satisfies this test by construction").
  It still runs, to catch a scenario that overrides liquidation to a fixed post-
  retirement date.
- Tax: every liquidity-event and tax-deferred-distribution derivation already carries
  an effective-rate estimate (Section 7.4); there is no candidate-dependent condition
  under which tax would be omitted, so this test is a structural always-pass, not a
  placeholder.

The `stress` test implements the deterministic half of Section 6.1's "the plan passes
the configured conservative deterministic scenario and/or the Monte Carlo Success
Threshold": it re-runs the candidate with every non-cash account's return haircut by
`Scenario.stress_return_haircut`, *relative to whatever this scenario's own return
already is* -- not `scenario_library.conservative_returns`'s absolute 4% floor. An
absolute floor was tried first and rejected: it makes every scenario at or above 4%
collapse to the identical solved WOA regardless of its own return assumption, which
would make the Phase 3 return-variant scenarios (conservative/expected/optimistic)
meaningless for WOA comparison (see `models.Scenario`'s docstring and the Phase 4 scope
note in docs/delivery-plan.md). It is deliberately *not* where the Monte Carlo half
lives -- running 10,000 simulations at every coarse-scan/bisection candidate would
defeat Section 6.3's own performance target, so `woa_solver.solve_woa` runs Monte Carlo
only once, at the final bisected candidate (Section 6.3 steps 3-4), and this function's
result is marked `Status.PLACEHOLDER` to signal it is one half of a compound test, not
the whole thing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .models import Scenario, Status
from .projection import ProjectionOutput, run_projection
from .spending import essential_fraction

LIQUID_CLASSES = {"immediate", "liquid"}


@dataclass(frozen=True)
class TestOutcome:
    name: str
    passed: bool
    detail: str
    status: Status = Status.CONFIRMED


@dataclass(frozen=True)
class RetirementTestSuite:
    candidate_date: date
    outcomes: list[TestOutcome]

    @property
    def all_passed(self) -> bool:
        return all(o.passed for o in self.outcomes)

    def first_failure(self) -> TestOutcome | None:
        for outcome in self.outcomes:
            if not outcome.passed:
                return outcome
        return None

    def by_name(self, name: str) -> TestOutcome:
        for outcome in self.outcomes:
            if outcome.name == name:
                return outcome
        raise KeyError(name)


def _retirement_period(projection: ProjectionOutput, retirement_date: date):
    on_or_after = [p for p in projection.periods if p.period_date >= retirement_date]
    if not on_or_after:
        raise ValueError(
            f"projection does not extend to the candidate retirement date {retirement_date}"
        )
    return on_or_after[0]


def liquidity_test(
    scenario: Scenario,
    projection: ProjectionOutput,
    retirement_date: date,
    annual_spending_total: Decimal,
) -> TestOutcome:
    period = _retirement_period(projection, retirement_date)
    household = scenario.household
    liquid_assets = sum(
        (
            balance
            for name, balance in period.account_balances.items()
            if household.accounts[name].liquidity_class in LIQUID_CLASSES
        ),
        Decimal("0"),
    )
    essential_monthly = annual_spending_total * essential_fraction(household.expense_categories) / 12
    required = essential_monthly * scenario.cash_reserve_months
    passed = liquid_assets >= required
    return TestOutcome(
        "liquidity",
        passed,
        f"liquid assets {liquid_assets} vs {scenario.cash_reserve_months}-month essential "
        f"reserve requirement {required}",
    )


def longevity_test(projection: ProjectionOutput) -> TestOutcome:
    shortfalls = [p for p in projection.periods if p.investable_assets <= 0]
    passed = not shortfalls
    detail = (
        "investable assets remain positive through the terminal age"
        if passed
        else f"investable assets reach {shortfalls[0].investable_assets} on {shortfalls[0].period_date}"
    )
    return TestOutcome("longevity", passed, detail)


def spending_test(projection: ProjectionOutput) -> TestOutcome:
    shortfalls = [p for p in projection.periods if p.warnings]
    passed = not shortfalls
    detail = (
        "essential and discretionary spending are fully funded every period"
        if passed
        else f"spending shortfall on {shortfalls[0].period_date}: {shortfalls[0].warnings[0]}"
    )
    return TestOutcome("spending", passed, detail)


def legacy_test(scenario: Scenario, projection: ProjectionOutput) -> TestOutcome:
    if not scenario.legacy_test_enabled:
        return TestOutcome("legacy", True, "disabled by default (Section 6.2)")
    terminal_period = projection.periods[-1]
    passed = terminal_period.net_worth >= scenario.legacy_floor
    return TestOutcome(
        "legacy",
        passed,
        f"terminal net worth {terminal_period.net_worth} vs legacy floor {scenario.legacy_floor}",
    )


def concentration_test(
    scenario: Scenario, projection: ProjectionOutput, retirement_date: date
) -> TestOutcome:
    period = _retirement_period(projection, retirement_date)
    passed = period.shares_outstanding == 0
    detail = (
        "retirement-linked liquidation (CR-005) fully unwinds employer equity by construction"
        if passed
        else f"{period.shares_outstanding} shares remain unliquidated at retirement"
    )
    return TestOutcome("concentration", passed, detail)


def tax_test() -> TestOutcome:
    return TestOutcome(
        "tax",
        True,
        "estimated taxes are embedded in every liquidity-event and distribution "
        "derivation (Section 7.4); structurally always satisfied",
    )


def stress_test(scenario: Scenario, retirement_date: date, terminal_age: int) -> TestOutcome:
    stressed = run_projection(
        scenario,
        terminal_age=terminal_age,
        retirement_date=retirement_date,
        return_haircut=scenario.stress_return_haircut,
    )
    longevity = longevity_test(stressed)
    spending = spending_test(stressed)
    passed = longevity.passed and spending.passed
    return TestOutcome(
        "stress",
        passed,
        f"deterministic conservative proxy (return haircut {scenario.stress_return_haircut}, "
        f"relative to this scenario's own {scenario.household.accounts['taxable'].annual_return.value} "
        "base return): "
        f"longevity {'pass' if longevity.passed else 'fail: ' + longevity.detail}, "
        f"spending {'pass' if spending.passed else 'fail: ' + spending.detail}",
        status=Status.PLACEHOLDER,
    )


def evaluate_deterministic_tests(
    scenario: Scenario,
    projection: ProjectionOutput,
    retirement_date: date,
    annual_spending_total: Decimal,
) -> RetirementTestSuite:
    outcomes = [
        liquidity_test(scenario, projection, retirement_date, annual_spending_total),
        longevity_test(projection),
        spending_test(projection),
        legacy_test(scenario, projection),
        concentration_test(scenario, projection, retirement_date),
        tax_test(),
    ]
    return RetirementTestSuite(retirement_date, outcomes)


def evaluate_all_tests(
    scenario: Scenario,
    projection: ProjectionOutput,
    retirement_date: date,
    terminal_age: int,
    annual_spending_total: Decimal,
) -> RetirementTestSuite:
    deterministic = evaluate_deterministic_tests(
        scenario, projection, retirement_date, annual_spending_total
    )
    stress = stress_test(scenario, retirement_date, terminal_age)
    return RetirementTestSuite(retirement_date, deterministic.outcomes + [stress])
