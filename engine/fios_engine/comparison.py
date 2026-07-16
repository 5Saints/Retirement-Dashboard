"""Scenario/decision comparison (PRD Section 8.2 Decision Output).

`compare_scenarios` runs each scenario's own WOA/SAS solve (Phase 2) and Monte Carlo
simulation (Phase 4) and reports the full Section 8.2 output: WOA impact, SAS impact,
success probability before/after, liquidity impact, legacy impact at ages 75/85/95, tax
impact, and risk impact. `status` reflects whether Monte Carlo actually ran on both
sides (`Status.CONFIRMED`) or was skipped via `Scenario.monte_carlo_enabled=False` on
either scenario (`Status.PLACEHOLDER`, success-probability fields `None`) -- the fast
deterministic-only path most tests use.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .dashboard import DashboardSummary, compute_dashboard_summary
from .estate import net_worth_at_age
from .models import Scenario, Status
from .monte_carlo import run_monte_carlo
from .projection import ProjectionOutput, run_projection
from .retirement_tests import LIQUID_CLASSES, essential_fraction
from .sas_solver import solve_sas
from .spending import first_year_spending


@dataclass(frozen=True)
class MetricSnapshot:
    scenario_name: str
    evaluated_at: date | None
    sas: Decimal | None
    freedom_margin: Decimal | None
    success_probability: float | None
    min_liquid_balance: Decimal | None
    liquid_years_of_core_coverage_at_retirement: Decimal | None
    legacy_at_75: Decimal | None
    legacy_at_85: Decimal | None
    legacy_at_95: Decimal | None
    cumulative_tax: Decimal | None
    peak_pre_retirement_concentration: Decimal | None


@dataclass(frozen=True)
class ScenarioComparison:
    baseline: MetricSnapshot
    alternative: MetricSnapshot
    woa_impact_months: int | None
    sas_impact_dollars: Decimal | None
    sas_impact_percent: Decimal | None
    liquidity_impact: Decimal | None
    legacy_impact: dict[int, Decimal | None]
    tax_impact: Decimal | None
    risk_impact: Decimal | None
    success_probability_before: float | None
    success_probability_after: float | None
    status: Status = Status.CONFIRMED


def _cumulative_tax(projection: ProjectionOutput) -> Decimal:
    total = Decimal("0")
    for period in projection.periods:
        total += period.estimated_taxes + period.distribution_tax
        total += sum((e.tax for e in period.liquidity_events), Decimal("0"))
    return total


def snapshot(
    scenario: Scenario, retirement_date: date | None = None, summary: DashboardSummary | None = None
) -> MetricSnapshot:
    """With `retirement_date=None` (default), solves this scenario's own WOA and
    evaluates at that date -- the right comparison for an assumption-only scenario
    (returns, inflation, tax, spending scale): "how does this change move my WOA?".
    Pass a precomputed `summary` to skip re-solving WOA/Monte Carlo when a caller (e.g.
    `retirement_readiness.compute_rrs`, `recommendation.py`) already has one for this
    scenario.

    Passing an explicit `retirement_date` instead evaluates the scenario AT that fixed
    date without re-solving WOA -- required for a retirement-timing decision (e.g.
    `scenario_library.retire_at_age`), since the WOA solver searches every candidate
    date independent of `household.planned_retirement_age` and would otherwise report
    the same solved WOA for every such scenario, masking the decision entirely."""
    if retirement_date is None:
        if summary is None:
            summary = compute_dashboard_summary(scenario)
        retirement_date = summary.fid if summary.fid is not None else scenario.household.retirement_date
        sas_value = summary.sas.sustainable_spending if summary.sas is not None else None
        freedom_margin = summary.freedom_margin
        success_probability = summary.success_probability
    else:
        sas_result = solve_sas(scenario, retirement_date)
        sas_value = sas_result.sustainable_spending if sas_result.bounded else None
        desired = first_year_spending(
            scenario.household.expense_categories, retirement_date.year, scenario.retirement_inflation_rate
        )
        freedom_margin = sas_value - desired if sas_value is not None else None
        success_probability = (
            run_monte_carlo(scenario, retirement_date, terminal_age=scenario.terminal_age).success_probability
            if scenario.monte_carlo_enabled
            else None
        )

    projection = run_projection(scenario, terminal_age=scenario.terminal_age, retirement_date=retirement_date)

    liquid_series = [
        sum(
            (
                balance
                for name, balance in p.account_balances.items()
                if scenario.household.accounts[name].liquidity_class in LIQUID_CLASSES
            ),
            Decimal("0"),
        )
        for p in projection.periods
    ]
    min_liquid = min(liquid_series) if liquid_series else None

    retirement_periods = [p for p in projection.periods if p.period_date >= retirement_date]
    liquid_at_retirement = (
        sum(
            (
                balance
                for name, balance in retirement_periods[0].account_balances.items()
                if scenario.household.accounts[name].liquidity_class in LIQUID_CLASSES
            ),
            Decimal("0"),
        )
        if retirement_periods
        else None
    )
    essential_annual = (
        sas_value * essential_fraction(scenario.household.expense_categories)
        if sas_value is not None
        else None
    )
    coverage_years = (
        liquid_at_retirement / essential_annual
        if liquid_at_retirement is not None and essential_annual
        else None
    )

    pre_retirement = [p for p in projection.periods if not p.is_retired]
    peak_concentration = (
        max((p.concentration_vs_net_worth for p in pre_retirement), default=Decimal("0"))
        if pre_retirement
        else Decimal("0")
    )

    return MetricSnapshot(
        scenario_name=scenario.name,
        evaluated_at=retirement_date,
        sas=sas_value,
        freedom_margin=freedom_margin,
        success_probability=success_probability,
        min_liquid_balance=min_liquid,
        liquid_years_of_core_coverage_at_retirement=coverage_years,
        legacy_at_75=net_worth_at_age(projection, scenario, 75),
        legacy_at_85=net_worth_at_age(projection, scenario, 85),
        legacy_at_95=net_worth_at_age(projection, scenario, 95),
        cumulative_tax=_cumulative_tax(projection),
        peak_pre_retirement_concentration=peak_concentration,
    )


def _month_diff(a: date, b: date) -> int:
    return (b.year - a.year) * 12 + (b.month - a.month)


def diff_snapshots(
    baseline_snapshot: MetricSnapshot,
    alternative_snapshot: MetricSnapshot,
    baseline_mc_enabled: bool,
    alternative_mc_enabled: bool,
) -> ScenarioComparison:
    """The comparison arithmetic, factored out of `compare_scenarios` so a caller that
    already has a precomputed baseline snapshot (e.g. `recommendation.py`, ranking many
    candidates against the *same* baseline) doesn't pay to re-solve the baseline's own
    WOA/Monte Carlo once per candidate."""
    woa_impact = (
        _month_diff(baseline_snapshot.evaluated_at, alternative_snapshot.evaluated_at)
        if baseline_snapshot.evaluated_at and alternative_snapshot.evaluated_at
        else None
    )
    sas_impact_dollars = (
        alternative_snapshot.sas - baseline_snapshot.sas
        if baseline_snapshot.sas is not None and alternative_snapshot.sas is not None
        else None
    )
    sas_impact_percent = (
        sas_impact_dollars / baseline_snapshot.sas
        if sas_impact_dollars is not None and baseline_snapshot.sas
        else None
    )
    liquidity_impact = (
        alternative_snapshot.min_liquid_balance - baseline_snapshot.min_liquid_balance
        if alternative_snapshot.min_liquid_balance is not None
        and baseline_snapshot.min_liquid_balance is not None
        else None
    )
    legacy_impact = {
        age: (
            getattr(alternative_snapshot, f"legacy_at_{age}") - getattr(baseline_snapshot, f"legacy_at_{age}")
            if getattr(alternative_snapshot, f"legacy_at_{age}") is not None
            and getattr(baseline_snapshot, f"legacy_at_{age}") is not None
            else None
        )
        for age in (75, 85, 95)
    }
    tax_impact = (
        alternative_snapshot.cumulative_tax - baseline_snapshot.cumulative_tax
        if alternative_snapshot.cumulative_tax is not None and baseline_snapshot.cumulative_tax is not None
        else None
    )
    risk_impact = (
        alternative_snapshot.peak_pre_retirement_concentration
        - baseline_snapshot.peak_pre_retirement_concentration
        if alternative_snapshot.peak_pre_retirement_concentration is not None
        and baseline_snapshot.peak_pre_retirement_concentration is not None
        else None
    )

    status = Status.CONFIRMED if baseline_mc_enabled and alternative_mc_enabled else Status.PLACEHOLDER
    return ScenarioComparison(
        baseline=baseline_snapshot,
        alternative=alternative_snapshot,
        woa_impact_months=woa_impact,
        sas_impact_dollars=sas_impact_dollars,
        sas_impact_percent=sas_impact_percent,
        liquidity_impact=liquidity_impact,
        legacy_impact=legacy_impact,
        tax_impact=tax_impact,
        risk_impact=risk_impact,
        success_probability_before=baseline_snapshot.success_probability,
        success_probability_after=alternative_snapshot.success_probability,
        status=status,
    )


def compare_scenarios(
    baseline: Scenario,
    alternative: Scenario,
    baseline_retirement_date: date | None = None,
    alternative_retirement_date: date | None = None,
) -> ScenarioComparison:
    """`*_retirement_date` overrides let a caller pin either side's evaluation date
    instead of re-solving WOA -- see `snapshot`'s docstring. A retirement-timing
    decision (`scenario_library.retire_at_age`) should pass
    `alternative_retirement_date=alternative.household.retirement_date` so the
    comparison reflects "what if I retire at this specific age" rather than
    re-discovering the same solved WOA on both sides."""
    baseline_snapshot = snapshot(baseline, baseline_retirement_date)
    alternative_snapshot = snapshot(alternative, alternative_retirement_date)
    return diff_snapshots(
        baseline_snapshot, alternative_snapshot, baseline.monte_carlo_enabled, alternative.monte_carlo_enabled
    )


def what_changed(comparison: ScenarioComparison, alternative: Scenario) -> list[str]:
    """Section 28: "generate a 'What changed?' summary identifying the assumptions
    responsible for movement in WOA, FID, RRS, RSP, FM, and SAS." RRS (Phase 4b) and RSP
    aren't computed yet, so this covers WOA/FID/FM/SAS only -- the fields this phase can
    actually produce -- plus the raw assumption edits recorded on the scenario itself.
    """
    lines = [
        f"{change.field_path}: {change.old_value} -> {change.new_value} ({change.reason})"
        for change in alternative.changes
    ]
    if comparison.woa_impact_months is not None:
        years, months = divmod(abs(comparison.woa_impact_months), 12)
        direction = "later" if comparison.woa_impact_months > 0 else "earlier"
        lines.append(f"WOA/FID moves {years}y {months}m {direction}")
    if comparison.sas_impact_dollars is not None:
        lines.append(
            f"SAS changes by {comparison.sas_impact_dollars} "
            f"({comparison.sas_impact_percent:.2%})" if comparison.sas_impact_percent is not None
            else f"SAS changes by {comparison.sas_impact_dollars}"
        )
    if comparison.alternative.freedom_margin is not None and comparison.baseline.freedom_margin is not None:
        fm_delta = comparison.alternative.freedom_margin - comparison.baseline.freedom_margin
        lines.append(f"Freedom Margin changes by {fm_delta}")
    if comparison.success_probability_before is not None and comparison.success_probability_after is not None:
        delta = comparison.success_probability_after - comparison.success_probability_before
        lines.append(
            f"Success probability moves from {comparison.success_probability_before:.1%} "
            f"to {comparison.success_probability_after:.1%} ({delta:+.1%})"
        )
    return lines
