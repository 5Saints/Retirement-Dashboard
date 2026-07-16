"""Tests for the Section 14 report model and its twelve builders (Phase 7)."""

from datetime import date
from decimal import Decimal

import pytest

from fios_engine import reporting, scenario_library as lib
from fios_engine.comparison import compare_scenarios
from fios_engine.recommendation_history import MODEL_VERSION
from fios_engine.retirement_readiness import material_valued_records
from fios_engine.seed import build_baseline_scenario

AS_OF = date(2026, 7, 15)


@pytest.fixture(scope="module")
def fast_scenario():
    scenario = build_baseline_scenario()
    scenario.monte_carlo_enabled = False
    return scenario


def _row(section, key, value):
    return next(r for r in section.rows if r.get(key) == value)


def test_every_report_carries_section_12_metadata(fast_scenario):
    report = reporting.executive_summary(fast_scenario, AS_OF)

    assert report.metadata.model_date == AS_OF
    assert report.metadata.scenario_name == fast_scenario.name
    assert report.metadata.model_version == MODEL_VERSION
    assert "confidence" in report.metadata.assumptions_note.lower()


def test_executive_summary_includes_core_dashboard_metrics(fast_scenario):
    report = reporting.executive_summary(fast_scenario, AS_OF)
    section = report.sections[0]
    metric_names = {row["metric"] for row in section.rows}

    assert "Work-Optional Age / FID" in metric_names
    assert "Retirement Readiness Score" in metric_names
    assert "Legacy Value at 75" in metric_names


def test_annual_projection_table_covers_every_projection_year(fast_scenario):
    report = reporting.annual_projection_table(fast_scenario, AS_OF)
    years = [row["year"] for row in report.sections[0].rows]

    assert years == sorted(years)
    assert fast_scenario.household.current_date.year in years


def test_balance_sheet_assets_minus_liabilities_matches_reported_net_worth(fast_scenario):
    report = reporting.balance_sheet(fast_scenario, AS_OF)
    assets_section = next(s for s in report.sections if s.heading == "Assets")
    liabilities_section = next(s for s in report.sections if s.heading == "Liabilities")
    summary_section = next(s for s in report.sections if s.heading == "Summary")

    total_assets = sum((row["balance"] for row in assets_section.rows), Decimal("0"))
    total_liabilities = sum((row["balance"] for row in liabilities_section.rows), Decimal("0"))
    reported_net_worth = _row(summary_section, "metric", "Net worth")["value"]

    assert total_assets - total_liabilities == reported_net_worth


def test_cash_flow_statement_totals_match_the_underlying_projection(fast_scenario):
    from fios_engine.projection import run_projection

    projection = run_projection(fast_scenario, terminal_age=fast_scenario.terminal_age)
    report = reporting.cash_flow_statement(fast_scenario, AS_OF, projection=projection)

    reported_total = sum((row["gross_income"] for row in report.sections[0].rows), Decimal("0"))
    actual_total = sum((p.gross_income for p in projection.periods), Decimal("0"))

    # Grouping the same 500+ terms into per-year subtotals before the grand total can
    # differ from a single flat sum by a sub-1e-20 artifact under fixed 28-digit Decimal
    # precision (same class of artifact test_monotonicity.py works around) -- well below
    # any unit this engine reports in (cents).
    assert abs(reported_total - actual_total) < Decimal("0.01")


def test_asset_allocation_percentages_reflect_total_assets_over_net_worth(fast_scenario):
    """Percentages are of *net worth*, not total assets -- with an outstanding mortgage
    (a liability, not an asset row here), total assets exceed net worth, so the
    percentages sum to somewhat more than 100%, not exactly 100%."""
    from fios_engine.projection import run_projection

    projection = run_projection(fast_scenario, terminal_age=fast_scenario.terminal_age)
    period = projection.periods[0]
    total_assets = sum(period.account_balances.values(), Decimal("0")) + period.equity_value + period.real_estate_value
    expected_percent = total_assets / period.net_worth * 100

    report = reporting.asset_allocation_report(fast_scenario, AS_OF)
    allocation = next(s for s in report.sections if s.heading == "Allocation")
    total_percent = sum((row["percent_of_net_worth"] for row in allocation.rows), Decimal("0"))

    assert abs(total_percent - expected_percent) < Decimal("0.01")


def test_company_equity_ledger_matches_household_data(fast_scenario):
    report = reporting.company_equity_ledger(fast_scenario, AS_OF)
    anchors = next(s for s in report.sections if s.heading == "Price-Path Anchors")
    events = next(s for s in report.sections if s.heading == "Liquidity Event Schedule")

    dates = [row["effective_date"] for row in anchors.rows]
    assert dates == sorted(dates)
    assert len(events.rows) == len(fast_scenario.household.liquidity_events)


def test_retirement_income_sources_flags_the_missing_ss_pension_gap(fast_scenario):
    report = reporting.retirement_income_sources(fast_scenario, AS_OF)
    notes = next(s for s in report.sections if s.heading == "Notes")

    assert "Social Security" in notes.rows[0]["note"]


def test_scenario_comparison_report_surfaces_the_recorded_change(fast_scenario):
    higher_tax = lib.higher_tax_on_company_payouts(fast_scenario)
    comparison = compare_scenarios(fast_scenario, higher_tax)

    report = reporting.scenario_comparison_report(fast_scenario, higher_tax, AS_OF, comparison=comparison)
    changes = next(s for s in report.sections if s.heading == "What Changed")

    assert any("tax_rate" in row["change"] for row in changes.rows)


def test_monte_carlo_report_reports_success_probability_when_run(fast_scenario):
    retirement_date = fast_scenario.household.retirement_date
    report = reporting.monte_carlo_report(fast_scenario, AS_OF, retirement_date=retirement_date)
    section = report.sections[0]

    simulations = _row(section, "metric", "Simulations")["value"]
    success = _row(section, "metric", "Success probability")["value"]

    assert simulations == 10_000
    assert success.endswith("%")


def test_legacy_report_matches_estate_legacy_values(fast_scenario):
    from fios_engine.estate import legacy_values

    values = legacy_values(fast_scenario)
    report = reporting.legacy_report(fast_scenario, AS_OF)
    ages = {row["age"]: row["legacy_value"] for row in report.sections[0].rows}

    assert ages == values


def test_assumption_register_matches_material_valued_records(fast_scenario):
    records = material_valued_records(fast_scenario.household)
    report = reporting.assumption_register(fast_scenario, AS_OF)

    assert len(report.sections[0].rows) == len(records)
    assert {row["assumption"] for row in report.sections[0].rows} == {r.name for r in records}


def test_audit_change_report_matches_scenario_changes(fast_scenario):
    higher_tax = lib.higher_tax_on_company_payouts(fast_scenario)

    report = reporting.audit_change_report(higher_tax, AS_OF)

    assert len(report.sections[0].rows) == len(higher_tax.changes)
    assert report.sections[0].rows[0]["field"] == higher_tax.changes[0].field_path


def test_audit_change_report_is_empty_for_the_baseline(fast_scenario):
    report = reporting.audit_change_report(fast_scenario, AS_OF)

    assert report.sections[0].rows == []
