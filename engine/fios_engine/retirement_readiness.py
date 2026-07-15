"""Retirement Readiness Score (PRD Section 25.1, CR-006).

Implements docs/rrs-normalization-spec.md exactly -- that document is the Section 23
pre-4b design deliverable ("Deliver the RRS normalization specification as a design
document before phase 4b begins"); read it first for the rationale behind every
constant below. This module is deliberately just the arithmetic that spec describes.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .dashboard import DashboardSummary, compute_dashboard_summary
from .models import Household, Scenario, Status
from .mortgage import placeholder_payoff_plan
from .projection import PRE_RETIREMENT_EFFECTIVE_TAX_RATE, run_projection
from .retirement_tests import LIQUID_CLASSES, essential_fraction
from .spending import first_year_spending
from .tax import TAX_DEFERRED_DISTRIBUTION_TAX_RATE
from .woa_solver import WOAResult, last_search_date

WOA_PROGRESS_WEIGHT = Decimal("0.35")
RSP_WEIGHT = Decimal("0.30")
FM_WEIGHT = Decimal("0.20")
LCR_WEIGHT = Decimal("0.10")
CRI_WEIGHT = Decimal("0.05")

FM_BAND = Decimal("0.5")  # Section 2.3: +/-50% clamp band
LCR_TARGET_MULTIPLE = Decimal("2")  # Section 2.4: target = 2x the cash-reserve minimum

STATUS_CONFIDENCE_WEIGHT = {
    Status.CONFIRMED: Decimal("1.00"),
    Status.DERIVED: Decimal("1.00"),
    Status.ASSUMPTION: Decimal("0.70"),
    Status.ESTIMATED: Decimal("0.50"),
    Status.PLACEHOLDER: Decimal("0.30"),
}


def _clamp(value: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    return max(lo, min(hi, value))


@dataclass(frozen=True)
class RRSComponent:
    name: str
    weight: Decimal
    raw_value: str
    score: Decimal


@dataclass(frozen=True)
class RRSResult:
    overall_score: Decimal
    components: list[RRSComponent]
    hard_constraint_failed: bool
    hard_constraint_detail: str | None
    confidence_percent: Decimal
    achievable: bool


def _woa_progress_score(scenario: Scenario, woa: WOAResult) -> tuple[Decimal, str]:
    if not woa.achievable or woa.candidate_date is None:
        return Decimal("0"), "Not Achievable"
    household = scenario.household
    boundary = last_search_date(scenario)
    total_window = (boundary - household.current_date).days
    if total_window <= 0:
        return Decimal("0"), f"WOA {woa.candidate_date} (no search window)"
    remaining = (boundary - woa.candidate_date).days
    progress = _clamp(Decimal(remaining) / Decimal(total_window), Decimal("0"), Decimal("1"))
    return Decimal("100") * progress, f"WOA {woa.candidate_date} (search window to {boundary})"


def _rsp_score(scenario: Scenario, success_probability: float | None) -> tuple[Decimal, str]:
    if success_probability is None:
        return Decimal("0"), "Monte Carlo not run"
    threshold = scenario.success_threshold
    probability = Decimal(str(success_probability))
    if probability >= threshold:
        return Decimal("100"), f"{success_probability:.1%} (>= {threshold:.0%} threshold)"
    return Decimal("100") * (probability / threshold), f"{success_probability:.1%} (< {threshold:.0%} threshold)"


def _fm_score(freedom_margin: Decimal | None, desired_spending: Decimal) -> tuple[Decimal, str]:
    if freedom_margin is None or desired_spending == 0:
        return Decimal("0"), "unavailable"
    ratio = freedom_margin / desired_spending
    score = Decimal("100") * _clamp((ratio + FM_BAND) / (FM_BAND * 2), Decimal("0"), Decimal("1"))
    return score, f"{ratio:+.1%} of desired spending"


def _lcr_score(scenario: Scenario, liquid_assets: Decimal, essential_annual: Decimal) -> tuple[Decimal, str]:
    if essential_annual == 0:
        return Decimal("0"), "unavailable"
    lcr_years = liquid_assets / essential_annual
    target_years = LCR_TARGET_MULTIPLE * (Decimal(scenario.cash_reserve_months) / 12)
    score = Decimal("100") * _clamp(lcr_years / target_years, Decimal("0"), Decimal("1"))
    return score, f"{lcr_years:.1f} years (target {target_years:.1f})"


def _cri_score(equity_value: Decimal, real_estate_value: Decimal, nw: Decimal) -> tuple[Decimal, str]:
    if nw <= 0:
        return Decimal("0"), "unavailable (non-positive net worth)"
    combined_concentration_ratio = (equity_value + real_estate_value) / nw
    score = Decimal("100") * _clamp(Decimal("1") - combined_concentration_ratio, Decimal("0"), Decimal("1"))
    return score, f"{combined_concentration_ratio:.1%} combined equity+real-estate exposure"


def _material_valued_statuses(household: Household) -> list[Status]:
    """Every material Valued/placeholder input this engine already flags Confirmed/
    Assumption/Placeholder/Estimated/Derived (Section 27), walked for the Section
    25.1/27 aggregate confidence indicator. See docs/rrs-normalization-spec.md Section 5
    for why this list and not a generic reflection scan."""
    statuses = [PRE_RETIREMENT_EFFECTIVE_TAX_RATE.status, TAX_DEFERRED_DISTRIBUTION_TAX_RATE.status]
    for account in household.accounts.values():
        statuses.append(account.annual_return.status)
    for event in household.liquidity_events:
        statuses.append(event.tax_rate.status)
    for real_estate in household.real_estate:
        statuses.append(real_estate.appreciation_rate.status)
    for anchor in household.equity_positions[0].anchors:
        statuses.append(anchor.status)
    mortgage = household.liabilities.get("primary_mortgage")
    if mortgage is not None and mortgage.opening_balance > 0 and mortgage.payoff_boundary_date is not None:
        plan = placeholder_payoff_plan(
            mortgage.opening_balance, household.current_date, mortgage.payoff_boundary_date
        )
        statuses.append(Status.PLACEHOLDER if plan.is_placeholder else Status.CONFIRMED)
    return statuses


def assumption_confidence_percent(household: Household) -> Decimal:
    statuses = _material_valued_statuses(household)
    if not statuses:
        return Decimal("100")
    total = sum((STATUS_CONFIDENCE_WEIGHT[status] for status in statuses), Decimal("0"))
    return Decimal("100") * total / len(statuses)


def compute_rrs(scenario: Scenario, summary: DashboardSummary | None = None) -> RRSResult:
    """Pass a precomputed `summary` (e.g. from `dashboard.compute_dashboard_summary`) to
    avoid re-solving WOA/Monte Carlo when a caller already has one -- `recommendation.py`
    ranks several candidates against the same scenario and would otherwise pay for the
    solve twice per candidate."""
    household = scenario.household
    if summary is None:
        summary = compute_dashboard_summary(scenario)
    woa = summary.woa

    evaluation_date = woa.candidate_date if woa.candidate_date is not None else household.retirement_date
    projection = run_projection(scenario, terminal_age=scenario.terminal_age, retirement_date=evaluation_date)
    at_evaluation = next((p for p in projection.periods if p.period_date >= evaluation_date), None)

    if woa.achievable and woa.tests is not None:
        hard_constraint_failed = not (
            woa.tests.by_name("longevity").passed and woa.tests.by_name("spending").passed
        )
        hard_constraint_detail = None if not hard_constraint_failed else (
            woa.tests.by_name("longevity").detail
            if not woa.tests.by_name("longevity").passed
            else woa.tests.by_name("spending").detail
        )
    else:
        hard_constraint_failed = True
        hard_constraint_detail = woa.not_achievable_reason or "WOA not achievable"

    woa_progress, woa_detail = _woa_progress_score(scenario, woa)
    rsp_score, rsp_detail = _rsp_score(scenario, summary.success_probability)

    desired_spending = first_year_spending(
        household.expense_categories, evaluation_date.year, scenario.retirement_inflation_rate
    )
    fm_score, fm_detail = _fm_score(summary.freedom_margin, desired_spending)

    if at_evaluation is not None:
        liquid_assets = sum(
            (
                balance
                for name, balance in at_evaluation.account_balances.items()
                if household.accounts[name].liquidity_class in LIQUID_CLASSES
            ),
            Decimal("0"),
        )
        essential_annual = (
            summary.sas.sustainable_spending * essential_fraction(household.expense_categories)
            if summary.sas is not None
            else desired_spending * essential_fraction(household.expense_categories)
        )
        lcr_score, lcr_detail = _lcr_score(scenario, liquid_assets, essential_annual)
        cri_score, cri_detail = _cri_score(
            at_evaluation.equity_value, at_evaluation.real_estate_value, at_evaluation.net_worth
        )
    else:
        lcr_score, lcr_detail = Decimal("0"), "unavailable"
        cri_score, cri_detail = Decimal("0"), "unavailable"

    components = [
        RRSComponent("Work-Optional Age progress", WOA_PROGRESS_WEIGHT, woa_detail, woa_progress),
        RRSComponent("Retirement Success Probability", RSP_WEIGHT, rsp_detail, rsp_score),
        RRSComponent("Freedom Margin", FM_WEIGHT, fm_detail, fm_score),
        RRSComponent("Liquidity Coverage", LCR_WEIGHT, lcr_detail, lcr_score),
        RRSComponent("Concentration Risk", CRI_WEIGHT, cri_detail, cri_score),
    ]
    overall = sum((c.weight * c.score for c in components), Decimal("0"))

    return RRSResult(
        overall_score=overall,
        components=components,
        hard_constraint_failed=hard_constraint_failed,
        hard_constraint_detail=hard_constraint_detail,
        confidence_percent=assumption_confidence_percent(household),
        achievable=woa.achievable,
    )
