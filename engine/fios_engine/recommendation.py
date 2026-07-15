"""Recommendation and Optimization Engine (PRD Section 26).

Generates a pool of actionable candidate decisions from the existing Phase 3/5
`scenario_library` builders, evaluates each against the baseline via
`comparison.diff_snapshots` (reusing one precomputed baseline snapshot/dashboard summary
across every candidate -- see that module's docstring), excludes any candidate whose WOA
comes back Not Achievable, ranks the survivors by the Section 26 optimization order, and
returns the top five with the full Section 26 output-field set.

"Must never recommend a materially earlier retirement if the configured Success
Threshold or essential-spending floor is violated" is enforced structurally, not by a
separate check here: `woa_solver.solve_woa` only reports a candidate date as achievable
once the deterministic longevity/essential-spending tests pass AND (when Monte Carlo is
enabled) the simulated success probability clears `Scenario.success_threshold` -- so a
candidate scenario whose WOA is Not Achievable has, by construction, already failed one
of those gates and is excluded. The gate checks `DashboardSummary.woa.achievable`
directly, not `MetricSnapshot.evaluated_at is None` -- `comparison.snapshot` falls back
to the household's own planned retirement date for informational display when WOA
fails, so `evaluated_at` is never actually `None`.

Ranking follows Section 26's stated optimization order as a lexicographic sort, not a
weighted score -- the PRD calls it an "order" (earliest WOA/FID, then required RSP, then
desired lifestyle/Freedom Margin, then tax efficiency, then liquidity resilience), and
estate value is explicitly "informational" -- it is reported but never breaks a tie.

Phase 6b (recommendation history: statuses, user responses, realized impact) is not
implemented here -- there is no persistence layer yet (no DB/API exists, see
delivery-plan.md), so `RecommendationHistory` tracking is out of scope for this phase.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Callable

from . import scenario_library as lib
from .comparison import ScenarioComparison, diff_snapshots, snapshot
from .dashboard import compute_dashboard_summary
from .models import DecisionType, Scenario
from .projection import add_months
from .retirement_readiness import RRSResult, assumption_confidence_percent, compute_rrs

TOP_N = 5

# Candidate amount/percentage grids -- engine-author choices, not PRD-specified numbers,
# the same status as any other reasonable default already flagged elsewhere (e.g.
# Scenario.discretionary_cut_fraction).
ROTH_CONVERSION_AMOUNTS = (Decimal("25000"), Decimal("50000"), Decimal("100000"))
DISCRETIONARY_CUT_FRACTIONS = (Decimal("0.10"), Decimal("0.25"), Decimal("0.50"))
REAL_ESTATE_PURCHASE_AMOUNT = Decimal("300000")
REAL_ESTATE_DECISION_LEAD_MONTHS = 24

# Engine-author confidence-level thresholds (Section 26 asks for "High, medium, or low,
# with a numerical confidence score where feasible" but does not specify the cutoffs).
CONFIDENCE_HIGH_THRESHOLD = Decimal("80")
CONFIDENCE_MEDIUM_THRESHOLD = Decimal("50")


@dataclass(frozen=True)
class CandidateAction:
    kind: str
    label: str
    decision_type: DecisionType | None
    timing: date
    amount: Decimal
    funding_source: str
    build: Callable[[Scenario], Scenario]


@dataclass(frozen=True)
class Recommendation:
    action: str
    decision_type: DecisionType | None
    timing: date
    amount: Decimal
    funding_source: str
    reason: str
    comparison: ScenarioComparison
    rrs_before: RRSResult
    rrs_after: RRSResult
    trade_offs: list[str]
    assumptions: list[str]
    confidence_level: str
    confidence_score: Decimal
    invalidation_conditions: list[str]
    trace: list[str]


@dataclass(frozen=True)
class RecommendationSet:
    recommendations: list[Recommendation]
    candidates_considered: int
    candidates_excluded_hard_constraint: int


def build_candidate_scenario(
    baseline: Scenario, kind: str, timing: date, amount: Decimal, funding_source: str
) -> Scenario:
    """Dispatches a candidate `kind` (see `CandidateAction.kind`) to the
    `scenario_library` builder that produces it. Public and reused by
    `recommendation_history.compute_realized_impact` (Phase 6b) so recomputing a
    previously-recommended action against a later, updated baseline goes through
    exactly the same construction path as the original recommendation did, rather
    than a second, potentially-diverging implementation."""
    if kind == "roth_conversion":
        return lib.roth_conversion(baseline, amount, timing, funding_source=funding_source, recurring=True)
    if kind == "discretionary_cut":
        return lib.reduce_discretionary_spending(baseline, amount)
    if kind == "proportional_withdrawal":
        return lib.use_proportional_withdrawals(baseline)
    if kind == "real_estate_purchase":
        return lib.purchase_additional_real_estate(baseline, amount, timing, funding_source=funding_source)
    if kind == "real_estate_sale":
        return lib.emergency_lake_home_sale(baseline, timing, funding_source=funding_source)
    raise ValueError(f"unknown candidate kind: {kind!r}")


def _generate_candidates(baseline: Scenario) -> list[CandidateAction]:
    household = baseline.household
    retirement_date = household.retirement_date
    real_estate_date = add_months(household.current_date, REAL_ESTATE_DECISION_LEAD_MONTHS)

    candidates: list[CandidateAction] = []

    for amount in ROTH_CONVERSION_AMOUNTS:
        candidates.append(
            CandidateAction(
                kind="roth_conversion",
                label=f"Convert ${amount:,.0f}/year to Roth starting at retirement",
                decision_type=DecisionType.ROTH_CONVERSION,
                timing=retirement_date,
                amount=amount,
                funding_source="taxable",
                build=lambda b, amount=amount: build_candidate_scenario(
                    b, "roth_conversion", retirement_date, amount, "taxable"
                ),
            )
        )

    for fraction in DISCRETIONARY_CUT_FRACTIONS:
        candidates.append(
            CandidateAction(
                kind="discretionary_cut",
                label=f"Reduce discretionary spending by {fraction:.0%}",
                decision_type=None,
                timing=retirement_date,
                amount=fraction,
                funding_source="",
                build=lambda b, fraction=fraction: build_candidate_scenario(
                    b, "discretionary_cut", retirement_date, fraction, ""
                ),
            )
        )

    candidates.append(
        CandidateAction(
            kind="proportional_withdrawal",
            label="Switch to proportional withdrawals across accounts",
            decision_type=None,
            timing=retirement_date,
            amount=Decimal("0"),
            funding_source="",
            build=lambda b: build_candidate_scenario(
                b, "proportional_withdrawal", retirement_date, Decimal("0"), ""
            ),
        )
    )

    candidates.append(
        CandidateAction(
            kind="real_estate_purchase",
            label=f"Purchase additional real estate (${REAL_ESTATE_PURCHASE_AMOUNT:,.0f})",
            decision_type=DecisionType.REAL_ESTATE_PURCHASE,
            timing=real_estate_date,
            amount=REAL_ESTATE_PURCHASE_AMOUNT,
            funding_source="taxable",
            build=lambda b: build_candidate_scenario(
                b, "real_estate_purchase", real_estate_date, REAL_ESTATE_PURCHASE_AMOUNT, "taxable"
            ),
        )
    )

    candidates.append(
        CandidateAction(
            kind="real_estate_sale",
            label="Emergency lake-home sale",
            decision_type=DecisionType.REAL_ESTATE_SALE,
            timing=real_estate_date,
            amount=Decimal("0"),
            funding_source="taxable",
            build=lambda b: build_candidate_scenario(
                b, "real_estate_sale", real_estate_date, Decimal("0"), "taxable"
            ),
        )
    )

    return candidates


def _reason(candidate: CandidateAction, comparison: ScenarioComparison) -> str:
    parts = [candidate.label + "."]
    if comparison.woa_impact_months is not None and comparison.woa_impact_months != 0:
        years, months = divmod(abs(comparison.woa_impact_months), 12)
        direction = "earlier" if comparison.woa_impact_months < 0 else "later"
        parts.append(f"Moves the Work-Optional Age {years}y {months}m {direction} than the baseline.")
    else:
        parts.append("Does not change the Work-Optional Age.")
    if comparison.sas_impact_dollars is not None and comparison.sas_impact_dollars != 0:
        direction = "Increases" if comparison.sas_impact_dollars > 0 else "Decreases"
        parts.append(
            f"{direction} sustainable annual spending by ${abs(comparison.sas_impact_dollars):,.0f}."
        )
    return " ".join(parts)


def _trade_offs(kind: str, comparison: ScenarioComparison) -> list[str]:
    trade_offs = []
    if comparison.tax_impact is not None and comparison.tax_impact > 0:
        trade_offs.append(f"Increases cumulative lifetime tax by ${comparison.tax_impact:,.0f}.")
    if comparison.liquidity_impact is not None and comparison.liquidity_impact < 0:
        trade_offs.append(
            f"Reduces the minimum liquidity buffer observed over the plan by "
            f"${abs(comparison.liquidity_impact):,.0f}."
        )
    if comparison.risk_impact is not None and comparison.risk_impact > 0:
        trade_offs.append("Increases peak pre-retirement concentration risk.")
    if kind == "discretionary_cut":
        trade_offs.append(
            "A lasting reduction in discretionary lifestyle spending (travel, hobbies, "
            "vehicles, home improvements, miscellaneous), not a one-time adjustment."
        )
    elif kind == "roth_conversion":
        trade_offs.append(
            "Converted funds move into the Roth account under normal Roth "
            "early-withdrawal/five-year rules, reducing near-term flexibility."
        )
    elif kind == "real_estate_purchase":
        trade_offs.append(
            "Ties up liquid capital in an illiquid asset with no assumed income or "
            "appreciation until specified (Section 4.8)."
        )
    elif kind == "real_estate_sale":
        trade_offs.append(
            "Permanently gives up the lake home's legacy and emergency-liquidity value (Section 4.8)."
        )
    if not trade_offs:
        trade_offs.append("No material adverse trade-off detected against the tracked metrics.")
    return trade_offs


def _invalidation_conditions(kind: str) -> list[str]:
    conditions = [
        "Actual investment returns fall materially below the modeled assumption.",
        "Household spending needs increase beyond the anchored essential/discretionary targets.",
    ]
    if kind == "roth_conversion":
        conditions.append(
            "Tax law changes eliminate or restrict Roth conversion eligibility or its current tax treatment."
        )
        conditions.append(
            "The household's marginal tax rate at conversion time is higher than assumed, "
            "reducing the conversion's benefit."
        )
    elif kind == "discretionary_cut":
        conditions.append(
            "The household is unwilling or unable to sustain the reduced discretionary spending level."
        )
    elif kind in ("real_estate_purchase", "real_estate_sale"):
        conditions.append(
            "Real-estate market conditions at the time of the transaction differ materially "
            "from the modeled value."
        )
    return conditions


def _trace(candidate: CandidateAction, comparison: ScenarioComparison) -> list[str]:
    accounts = {candidate.funding_source} if candidate.funding_source else set()
    if candidate.kind == "roth_conversion":
        accounts |= {"401k", "roth"}
    elif candidate.kind in ("real_estate_purchase", "real_estate_sale"):
        accounts |= {"real_estate"}
    return [
        f"Decision: {candidate.kind}, effective {candidate.timing}, amount {candidate.amount}, "
        f"funding source '{candidate.funding_source or 'n/a'}'.",
        f"Evaluated via woa_solver.solve_woa and monte_carlo.run_monte_carlo at candidate "
        f"WOA {comparison.alternative.evaluated_at}.",
        "Comparison computed by comparison.diff_snapshots against the baseline scenario's own solved WOA.",
        f"Affected accounts/entities: {', '.join(sorted(accounts)) or 'n/a'}.",
    ]


def _confidence(candidate_scenario: Scenario) -> tuple[str, Decimal]:
    score = assumption_confidence_percent(candidate_scenario.household)
    if score >= CONFIDENCE_HIGH_THRESHOLD:
        level = "High"
    elif score >= CONFIDENCE_MEDIUM_THRESHOLD:
        level = "Medium"
    else:
        level = "Low"
    return level, score


def _assumptions(candidate_scenario: Scenario) -> list[str]:
    return [
        f"{change.field_path}: {change.old_value} -> {change.new_value} ({change.reason})"
        for change in candidate_scenario.changes
    ]


def _ranking_key(recommendation: Recommendation):
    """Section 26's optimization order, applied as a lexicographic sort: earliest
    WOA/FID first, then higher required-success-probability margin, then higher
    Freedom Margin (desired lifestyle), then lower tax impact (tax efficiency), then
    higher liquidity impact (liquidity resilience). Estate value is deliberately not a
    sort key -- Section 26: "then informational estate value.\""""
    comparison = recommendation.comparison
    rsp = comparison.success_probability_after if comparison.success_probability_after is not None else 0.0
    fm = float(comparison.alternative.freedom_margin) if comparison.alternative.freedom_margin is not None else 0.0
    tax = float(comparison.tax_impact) if comparison.tax_impact is not None else 0.0
    liquidity = float(comparison.liquidity_impact) if comparison.liquidity_impact is not None else 0.0
    return (comparison.alternative.evaluated_at, -rsp, -fm, tax, -liquidity)


def generate_recommendations(baseline: Scenario, top_n: int = TOP_N) -> RecommendationSet:
    baseline_summary = compute_dashboard_summary(baseline)
    baseline_snapshot = snapshot(baseline, summary=baseline_summary)
    baseline_rrs = compute_rrs(baseline, summary=baseline_summary)

    candidates = _generate_candidates(baseline)
    evaluated: list[Recommendation] = []
    excluded = 0

    for candidate in candidates:
        candidate_scenario = candidate.build(baseline)
        candidate_summary = compute_dashboard_summary(candidate_scenario)

        if not candidate_summary.woa.achievable:
            # `comparison.snapshot` falls back to the household's own planned
            # retirement date when WOA is Not Achievable (so it always has *some*
            # date to report informationally) -- `evaluated_at is None` would never
            # be true, so the hard-constraint gate must check `woa.achievable`
            # directly, before that fallback happens.
            excluded += 1
            continue

        candidate_snapshot = snapshot(candidate_scenario, summary=candidate_summary)

        comparison = diff_snapshots(
            baseline_snapshot,
            candidate_snapshot,
            baseline.monte_carlo_enabled,
            candidate_scenario.monte_carlo_enabled,
        )
        candidate_rrs = compute_rrs(candidate_scenario, summary=candidate_summary)
        confidence_level, confidence_score = _confidence(candidate_scenario)

        evaluated.append(
            Recommendation(
                action=candidate.label,
                decision_type=candidate.decision_type,
                timing=candidate.timing,
                amount=candidate.amount,
                funding_source=candidate.funding_source,
                reason=_reason(candidate, comparison),
                comparison=comparison,
                rrs_before=baseline_rrs,
                rrs_after=candidate_rrs,
                trade_offs=_trade_offs(candidate.kind, comparison),
                assumptions=_assumptions(candidate_scenario),
                confidence_level=confidence_level,
                confidence_score=confidence_score,
                invalidation_conditions=_invalidation_conditions(candidate.kind),
                trace=_trace(candidate, comparison),
            )
        )

    ranked = sorted(evaluated, key=_ranking_key)
    return RecommendationSet(
        recommendations=ranked[:top_n],
        candidates_considered=len(candidates),
        candidates_excluded_hard_constraint=excluded,
    )
