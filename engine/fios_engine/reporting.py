"""Reporting (PRD Section 14; Phase 7).

A generic `Report`/`ReportSection` model plus twelve builder functions -- one per
Section 14 report type -- avoids twelve bespoke schemas: every builder assembles the
same `Report(title, metadata, sections)` shape from data this package already computes
elsewhere (dashboard, projection, comparison, monte_carlo, estate, retirement_readiness).
`report_export.py` exports any `Report` to CSV/JSON/PDF/Excel without knowing which of
the twelve it is.

Section 12: "Reports must display model date, scenario name, assumptions, and model
version" -- every `Report.metadata` carries all four (`assumptions_note` summarizes the
Section 25.1/27 aggregate confidence percent; the full per-input breakdown is its own
report -- see `assumption_register` below).

No report builder calls `date.today()` -- `as_of` is always caller-supplied (Section 27
reproducibility), matching the rest of this engine. Several builders accept an already-
computed result (`summary`, `projection`, `comparison`, `result`) so a caller producing
several reports for the same scenario (e.g. a "generate all reports" endpoint) doesn't
pay to re-solve WOA/Monte Carlo/run the projection once per report.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .comparison import ScenarioComparison, compare_scenarios, what_changed
from .dashboard import DashboardSummary, compute_dashboard_summary
from .estate import LEGACY_REPORT_AGES, legacy_values
from .models import Scenario
from .monte_carlo import MonteCarloResult, run_monte_carlo
from .projection import ProjectionOutput, run_projection
from .recommendation_history import MODEL_VERSION
from .retirement_readiness import assumption_confidence_percent, compute_rrs, material_valued_records


@dataclass(frozen=True)
class ReportMetadata:
    model_date: date
    scenario_name: str
    model_version: str
    assumptions_note: str


@dataclass(frozen=True)
class ReportSection:
    heading: str
    rows: list[dict[str, object]]


@dataclass(frozen=True)
class Report:
    title: str
    metadata: ReportMetadata
    sections: list[ReportSection]


def _metadata(scenario: Scenario, as_of: date) -> ReportMetadata:
    confidence = assumption_confidence_percent(scenario.household)
    return ReportMetadata(
        model_date=as_of,
        scenario_name=scenario.name,
        model_version=MODEL_VERSION,
        assumptions_note=(
            f"Aggregate assumption confidence: {confidence:.1f}% "
            "(see Assumption Register report for the full per-input breakdown)"
        ),
    )


def _period_at_or_after(projection: ProjectionOutput, target: date):
    matches = [p for p in projection.periods if p.period_date >= target]
    return matches[0] if matches else projection.periods[-1]


def executive_summary(scenario: Scenario, as_of: date, summary: DashboardSummary | None = None) -> Report:
    """Section 13's dashboard cards collapsed onto one page: primary answer, WOA/FID,
    SAS, Freedom Margin, success probability, RRS, and legacy at 75/85/95."""
    if summary is None:
        summary = compute_dashboard_summary(scenario)
    rrs = compute_rrs(scenario, summary)
    legacy = legacy_values(scenario, retirement_date=summary.fid, terminal_age=scenario.terminal_age)
    can_retire_today = (
        summary.woa.achievable
        and summary.woa.candidate_date is not None
        and summary.woa.candidate_date <= scenario.household.current_date
    )
    rows = [
        {"metric": "Can retire today", "value": "Yes" if can_retire_today else "No"},
        {
            "metric": "Work-Optional Age / FID",
            "value": str(summary.woa.candidate_date) if summary.woa.candidate_date else "Not Achievable",
        },
        {
            "metric": "Sustainable Annual Spending",
            "value": str(summary.sas.sustainable_spending) if summary.sas is not None else "N/A",
        },
        {
            "metric": "Freedom Margin",
            "value": str(summary.freedom_margin) if summary.freedom_margin is not None else "N/A",
        },
        {
            "metric": "Success Probability",
            "value": f"{summary.success_probability:.1%}" if summary.success_probability is not None else "N/A",
        },
        {"metric": "Retirement Readiness Score", "value": f"{rrs.overall_score:.1f}/100"},
        {"metric": "Legacy Value at 75", "value": legacy.get(75)},
        {"metric": "Legacy Value at 85", "value": legacy.get(85)},
        {"metric": "Legacy Value at 95", "value": legacy.get(95)},
    ]
    return Report("Executive Summary", _metadata(scenario, as_of), [ReportSection("Key Metrics", rows)])


def annual_projection_table(
    scenario: Scenario,
    as_of: date,
    retirement_date: date | None = None,
    terminal_age: int | None = None,
    projection: ProjectionOutput | None = None,
) -> Report:
    if projection is None:
        projection = run_projection(
            scenario, terminal_age=terminal_age or scenario.terminal_age, retirement_date=retirement_date
        )
    years = sorted({p.period_date.year for p in projection.periods})
    rows = []
    for year in years:
        period = projection.last_period_in_year(year)
        rows.append(
            {
                "year": year,
                "retired": period.is_retired,
                "gross_income": period.gross_income,
                "estimated_taxes": period.estimated_taxes,
                "actual_spending": period.actual_spending,
                "net_worth": period.net_worth,
                "investable_assets": period.investable_assets,
            }
        )
    return Report(
        "Full Annual Projection Table", _metadata(scenario, as_of), [ReportSection("Annual Projection", rows)]
    )


def balance_sheet(
    scenario: Scenario,
    as_of: date,
    on_date: date | None = None,
    projection: ProjectionOutput | None = None,
) -> Report:
    target = on_date or scenario.household.current_date
    if projection is None:
        projection = run_projection(scenario, terminal_age=scenario.terminal_age)
    period = _period_at_or_after(projection, target)
    asset_rows = [{"asset": f"Account: {name}", "balance": balance} for name, balance in period.account_balances.items()]
    asset_rows.append({"asset": "Company equity", "balance": period.equity_value})
    asset_rows.append({"asset": "Real estate", "balance": period.real_estate_value})
    liability_rows = [{"liability": "Mortgage", "balance": period.mortgage_balance}]
    summary_rows = [
        {"metric": "As-of date", "value": period.period_date},
        {"metric": "Net worth", "value": period.net_worth},
        {"metric": "Investable assets", "value": period.investable_assets},
    ]
    return Report(
        "Balance Sheet",
        _metadata(scenario, as_of),
        [
            ReportSection("Assets", asset_rows),
            ReportSection("Liabilities", liability_rows),
            ReportSection("Summary", summary_rows),
        ],
    )


def cash_flow_statement(
    scenario: Scenario,
    as_of: date,
    retirement_date: date | None = None,
    terminal_age: int | None = None,
    projection: ProjectionOutput | None = None,
) -> Report:
    if projection is None:
        projection = run_projection(
            scenario, terminal_age=terminal_age or scenario.terminal_age, retirement_date=retirement_date
        )
    years = sorted({p.period_date.year for p in projection.periods})
    rows = []
    for year in years:
        year_periods = [p for p in projection.periods if p.period_date.year == year]
        liquidity_net = sum(
            (sum((e.net for e in p.liquidity_events), Decimal("0")) for p in year_periods), Decimal("0")
        )
        rows.append(
            {
                "year": year,
                "gross_income": sum((p.gross_income for p in year_periods), Decimal("0")),
                "estimated_taxes": sum((p.estimated_taxes for p in year_periods), Decimal("0")),
                "distribution_tax": sum((p.distribution_tax for p in year_periods), Decimal("0")),
                "conversion_tax": sum((p.conversion_tax for p in year_periods), Decimal("0")),
                "debt_service": sum((p.debt_service for p in year_periods), Decimal("0")),
                "actual_spending": sum((p.actual_spending or Decimal("0") for p in year_periods), Decimal("0")),
                "liquidity_event_net_proceeds": liquidity_net,
            }
        )
    return Report("Cash-Flow Statement", _metadata(scenario, as_of), [ReportSection("Annual Cash Flow", rows)])


def asset_allocation_report(
    scenario: Scenario,
    as_of: date,
    on_date: date | None = None,
    projection: ProjectionOutput | None = None,
) -> Report:
    target = on_date or scenario.household.current_date
    if projection is None:
        projection = run_projection(scenario, terminal_age=scenario.terminal_age)
    period = _period_at_or_after(projection, target)
    nw = period.net_worth
    rows = [
        {
            "asset_class": f"Account: {name}",
            "balance": balance,
            "percent_of_net_worth": (balance / nw * 100) if nw else Decimal("0"),
        }
        for name, balance in period.account_balances.items()
    ]
    rows.append(
        {
            "asset_class": "Company equity",
            "balance": period.equity_value,
            "percent_of_net_worth": (period.equity_value / nw * 100) if nw else Decimal("0"),
        }
    )
    rows.append(
        {
            "asset_class": "Real estate",
            "balance": period.real_estate_value,
            "percent_of_net_worth": (period.real_estate_value / nw * 100) if nw else Decimal("0"),
        }
    )
    concentration_rows = [
        {"metric": "Concentration vs net worth", "value": f"{period.concentration_vs_net_worth:.1%}"},
        {"metric": "Concentration vs investable assets", "value": f"{period.concentration_vs_investable:.1%}"},
    ]
    return Report(
        "Asset-Allocation Report",
        _metadata(scenario, as_of),
        [ReportSection("Allocation", rows), ReportSection("Concentration", concentration_rows)],
    )


def company_equity_ledger(scenario: Scenario, as_of: date) -> Report:
    household = scenario.household
    equity_position = household.equity_positions[0]
    anchor_rows = [
        {"effective_date": a.effective_date, "price": a.price, "status": a.status.value}
        for a in sorted(equity_position.anchors, key=lambda a: a.effective_date)
    ]
    event_rows = []
    for index, event in enumerate(household.liquidity_events, start=1):
        event_date = event.resolve_date(household.retirement_date)
        result = event.derive(household.retirement_date)
        event_rows.append(
            {
                "event": f"Event {index}",
                "date": event_date,
                "shares_sold": event.shares_sold,
                "gross": result.gross,
                "tax": result.tax,
                "net": result.net,
                "tax_rate_status": event.tax_rate.status.value,
            }
        )
    return Report(
        "Company-Equity Ledger and Event Schedule",
        _metadata(scenario, as_of),
        [ReportSection("Price-Path Anchors", anchor_rows), ReportSection("Liquidity Event Schedule", event_rows)],
    )


def retirement_income_sources(scenario: Scenario, as_of: date) -> Report:
    """Section 4.1: the baseline household has no Social Security or pension income --
    this report is portfolio-withdrawal-only until such a stream exists, flagged so an
    empty/short table doesn't read as a bug."""
    rows = [
        {
            "source": stream.name,
            "annual_amount": stream.annual_amount,
            "growth_rate": stream.growth_rate,
            "start_date": stream.start_date,
            "end_date": stream.end_date,
        }
        for stream in scenario.household.income_streams
    ]
    note_rows = [
        {
            "note": (
                "No Social Security or pension income streams are modeled for this "
                "household (Section 4.1); retirement income is entirely portfolio "
                "withdrawals per the scenario's configured withdrawal order/strategy."
            )
        }
    ]
    return Report(
        "Retirement-Income Sources",
        _metadata(scenario, as_of),
        [ReportSection("Income Streams", rows), ReportSection("Notes", note_rows)],
    )


def scenario_comparison_report(
    baseline: Scenario,
    alternative: Scenario,
    as_of: date,
    baseline_retirement_date: date | None = None,
    alternative_retirement_date: date | None = None,
    comparison: ScenarioComparison | None = None,
) -> Report:
    if comparison is None:
        comparison = compare_scenarios(
            baseline, alternative, baseline_retirement_date, alternative_retirement_date
        )
    changes = what_changed(comparison, alternative)
    metric_rows = [
        {"metric": "WOA impact (months)", "value": comparison.woa_impact_months},
        {"metric": "SAS impact ($)", "value": comparison.sas_impact_dollars},
        {"metric": "SAS impact (%)", "value": comparison.sas_impact_percent},
        {"metric": "Liquidity impact", "value": comparison.liquidity_impact},
        {"metric": "Tax impact", "value": comparison.tax_impact},
        {"metric": "Risk impact", "value": comparison.risk_impact},
        {"metric": "Success probability before", "value": comparison.success_probability_before},
        {"metric": "Success probability after", "value": comparison.success_probability_after},
    ]
    legacy_rows = [{"age": age, "impact": value} for age, value in comparison.legacy_impact.items()]
    change_rows = [{"change": line} for line in changes]
    return Report(
        "Scenario-Comparison Report",
        _metadata(alternative, as_of),
        [
            ReportSection("Metric Impacts", metric_rows),
            ReportSection("Legacy Impact", legacy_rows),
            ReportSection("What Changed", change_rows),
        ],
    )


def monte_carlo_report(
    scenario: Scenario,
    as_of: date,
    retirement_date: date | None = None,
    terminal_age: int | None = None,
    result: MonteCarloResult | None = None,
) -> Report:
    if result is None and retirement_date is None:
        summary = compute_dashboard_summary(scenario)
        retirement_date = summary.fid
        result = summary.woa.monte_carlo_result
    if result is None and retirement_date is not None:
        result = run_monte_carlo(scenario, retirement_date, terminal_age=terminal_age or scenario.terminal_age)
    if result is None:
        rows = [{"note": "Monte Carlo unavailable (WOA not achievable and no retirement_date supplied)"}]
        return Report("Monte Carlo Report", _metadata(scenario, as_of), [ReportSection("Result", rows)])
    rows = [
        {"metric": "Simulations", "value": result.num_simulations},
        {"metric": "Seed", "value": result.seed},
        {"metric": "Success probability", "value": f"{result.success_probability:.1%}"},
        {"metric": "Median terminal balance", "value": result.median_terminal_balance},
        {"metric": "10th percentile", "value": result.percentile_10},
        {"metric": "25th percentile", "value": result.percentile_25},
        {"metric": "75th percentile", "value": result.percentile_75},
        {"metric": "90th percentile", "value": result.percentile_90},
        {"metric": "Median of minimum portfolio balance", "value": result.minimum_portfolio_balance_median},
    ]
    return Report("Monte Carlo Report", _metadata(scenario, as_of), [ReportSection("Simulation Results", rows)])


def legacy_report(
    scenario: Scenario,
    as_of: date,
    retirement_date: date | None = None,
    terminal_age: int | None = None,
) -> Report:
    """Section 6.1/24: informational only, never gates or delays WOA/SAS."""
    values = legacy_values(scenario, retirement_date=retirement_date, terminal_age=terminal_age)
    rows = [{"age": age, "legacy_value": values.get(age)} for age in LEGACY_REPORT_AGES]
    note_rows = [
        {"note": "Informational only -- legacy value never gates or delays WOA/SAS (Section 6.1/24)."}
    ]
    return Report(
        "Legacy Report",
        _metadata(scenario, as_of),
        [ReportSection("Legacy Value by Age", rows), ReportSection("Notes", note_rows)],
    )


def assumption_register(scenario: Scenario, as_of: date) -> Report:
    records = material_valued_records(scenario.household)
    rows = [
        {"assumption": r.name, "value": r.value, "status": r.status.value, "source": r.source} for r in records
    ]
    return Report("Assumption Register", _metadata(scenario, as_of), [ReportSection("Material Assumptions", rows)])


def audit_change_report(scenario: Scenario, as_of: date) -> Report:
    rows = [
        {
            "field": change.field_path,
            "old_value": change.old_value,
            "new_value": change.new_value,
            "source": change.source,
            "reason": change.reason,
            "effective_date": change.effective_date,
        }
        for change in scenario.changes
    ]
    return Report("Audit / Change Report", _metadata(scenario, as_of), [ReportSection("Assumption Changes", rows)])
