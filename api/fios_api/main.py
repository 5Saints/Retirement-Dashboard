"""Minimal FastAPI layer over `fios_engine` (PRD Section 16/17.1; Phase 8+ scope).

Implements Section 17.1's eight endpoints, each wrapping an existing engine function
rather than reimplementing calculation logic -- exactly the reuse `docs/architecture.md`
promised ("the same engine will back the future web API... without modification"):

- `POST /scenarios/{id}/calculate`         -> dashboard summary + RRS + legacy + warnings
- `POST /scenarios/{id}/monte-carlo`       -> `monte_carlo.run_monte_carlo`
- `POST /scenarios/{id}/decisions/evaluate`-> clone + `Household.decisions` + `comparison.compare_scenarios`
- `GET  /scenarios/{id}/dashboard`         -> `reporting.executive_summary`
- `GET  /scenarios/{id}/projection`        -> `reporting.annual_projection_table`
- `POST /scenarios/{id}/clone`             -> `scenario_engine.clone_scenario`
- `POST /reports`                         -> any of the 12 `reporting.py` builders + any
                                              of the 4 `report_export.py` exporters
- `GET  /audit-events`                    -> flattened `Scenario.changes`

Plus `GET /scenarios` (listing) -- not in Section 17.1's list, but a store with no way to
discover what's in it isn't usable; kept deliberately small (id/name/parent only).

No database, no auth (Section 15 unaddressed), no frontend -- see `ScenarioStore`'s own
docstring. Every date-bearing parameter is caller-supplied, never `date.today()` (Section
27 reproducibility, the same rule the engine itself follows throughout).
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import Response
from fios_engine import report_export, reporting
from fios_engine.comparison import compare_scenarios, snapshot, what_changed
from fios_engine.dashboard import compute_dashboard_summary
from fios_engine.estate import legacy_values
from fios_engine.json_encoding import FiosJSONEncoder
from fios_engine.models import Decision, DecisionType, Scenario
from fios_engine.monte_carlo import DEFAULT_SEED, DEFAULT_SIMULATIONS, run_monte_carlo
from fios_engine.retirement_readiness import compute_rrs
from fios_engine.scenario_engine import clone_scenario
from pydantic import BaseModel

from .store import ScenarioStore

REPORT_BUILDERS = {
    "executive_summary": lambda s, ao, alt: reporting.executive_summary(s, ao),
    "annual_projection_table": lambda s, ao, alt: reporting.annual_projection_table(s, ao),
    "balance_sheet": lambda s, ao, alt: reporting.balance_sheet(s, ao),
    "cash_flow_statement": lambda s, ao, alt: reporting.cash_flow_statement(s, ao),
    "asset_allocation": lambda s, ao, alt: reporting.asset_allocation_report(s, ao),
    "company_equity_ledger": lambda s, ao, alt: reporting.company_equity_ledger(s, ao),
    "retirement_income_sources": lambda s, ao, alt: reporting.retirement_income_sources(s, ao),
    "monte_carlo": lambda s, ao, alt: reporting.monte_carlo_report(s, ao),
    "legacy": lambda s, ao, alt: reporting.legacy_report(s, ao),
    "assumption_register": lambda s, ao, alt: reporting.assumption_register(s, ao),
    "audit_change": lambda s, ao, alt: reporting.audit_change_report(s, ao),
    "scenario_comparison": lambda s, ao, alt: reporting.scenario_comparison_report(s, alt, ao),
}

EXPORTERS = {
    "json": (report_export.export_json, "application/json"),
    "csv": (report_export.export_csv, "text/csv"),
    "excel": (report_export.export_excel, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    "pdf": (report_export.export_pdf, "application/pdf"),
}


class CloneRequest(BaseModel):
    new_name: str


class DecisionRequest(BaseModel):
    decision_type: DecisionType
    effective_date: date
    amount: Decimal
    funding_source: str = ""
    recurring_effect: bool = True
    description: str = ""


class MonteCarloRequest(BaseModel):
    retirement_date: date | None = None
    terminal_age: int | None = None
    num_simulations: int = DEFAULT_SIMULATIONS
    seed: int = DEFAULT_SEED


class ReportRequest(BaseModel):
    scenario_id: str
    report_type: str
    format: str = "json"
    as_of: date
    alternative_scenario_id: str | None = None


def json_response(value: object, status_code: int = 200) -> Response:
    """Bypasses FastAPI's default `jsonable_encoder` (which turns `Decimal` into `int`/
    `float`, a precision regression this engine avoids everywhere else) in favor of the
    shared `FiosJSONEncoder` every other JSON-producing part of this engine already
    uses."""
    return Response(
        content=json.dumps(value, cls=FiosJSONEncoder), media_type="application/json", status_code=status_code
    )


def create_app(store: ScenarioStore | None = None) -> FastAPI:
    app = FastAPI(title="FIOS API", version="0.1.0")
    app.state.store = store if store is not None else ScenarioStore()

    def get_store() -> ScenarioStore:
        return app.state.store

    def get_scenario(scenario_id: str, store: ScenarioStore = Depends(get_store)) -> Scenario:
        try:
            return store.get(scenario_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/scenarios")
    def list_scenarios(store: ScenarioStore = Depends(get_store)):
        return json_response(
            [
                {"id": scenario_id, "parent_name": store.get(scenario_id).parent_name}
                for scenario_id in store.list_ids()
            ]
        )

    @app.post("/scenarios/{scenario_id}/calculate")
    def calculate(scenario_id: str, scenario: Scenario = Depends(get_scenario)):
        """Section 17's "minimum engine output": WOA/FID/SAS/Freedom Margin, pass/fail
        tests (inside `woa.tests`), risk/liquidity/legacy/tax metrics (`snapshot`), RRS,
        collected warnings, and the solver's own candidate trace."""
        summary = compute_dashboard_summary(scenario)
        rrs = compute_rrs(scenario, summary)
        metrics = snapshot(scenario, summary=summary)
        retirement_date = summary.fid if summary.fid is not None else scenario.household.retirement_date
        legacy = legacy_values(scenario, retirement_date=retirement_date, terminal_age=scenario.terminal_age)
        return json_response(
            {
                "scenario_name": scenario.name,
                "woa": summary.woa,
                "fid": summary.fid,
                "sas": summary.sas,
                "freedom_margin": summary.freedom_margin,
                "success_probability": summary.success_probability,
                "retirement_readiness_score": rrs,
                "metrics": metrics,
                "legacy_value": legacy,
            }
        )

    @app.post("/scenarios/{scenario_id}/monte-carlo")
    def monte_carlo_endpoint(
        scenario_id: str, body: MonteCarloRequest = MonteCarloRequest(), scenario: Scenario = Depends(get_scenario)
    ):
        retirement_date = body.retirement_date
        if retirement_date is None:
            summary = compute_dashboard_summary(scenario)
            if summary.fid is None:
                raise HTTPException(422, "WOA not achievable for this scenario; supply retirement_date explicitly")
            retirement_date = summary.fid
        result = run_monte_carlo(
            scenario,
            retirement_date,
            terminal_age=body.terminal_age,
            num_simulations=body.num_simulations,
            seed=body.seed,
        )
        return json_response(result)

    @app.post("/scenarios/{scenario_id}/decisions/evaluate")
    def evaluate_decision(
        scenario_id: str, body: DecisionRequest, store: ScenarioStore = Depends(get_store)
    ):
        baseline = get_scenario(scenario_id, store)
        alternative = clone_scenario(baseline, f"{baseline.name} + decision (evaluation)")
        alternative.household.decisions.append(
            Decision(
                decision_type=body.decision_type,
                effective_date=body.effective_date,
                amount=body.amount,
                funding_source=body.funding_source,
                recurring_effect=body.recurring_effect,
                description=body.description,
            )
        )
        try:
            comparison = compare_scenarios(baseline, alternative)
        except KeyError as exc:
            # A Decision's funding_source/description that doesn't name a real account
            # or real-estate property surfaces deep inside run_projection as a raw
            # KeyError (Section 18: the engine never silently defaults an unresolvable
            # reference) -- translate that at the API boundary into a clean 422 rather
            # than letting it escape as an unhandled 500.
            raise HTTPException(422, f"Decision references an unknown account/property: {exc}") from exc
        return json_response({"comparison": comparison, "what_changed": what_changed(comparison, alternative)})

    @app.get("/scenarios/{scenario_id}/dashboard")
    def dashboard_endpoint(scenario_id: str, as_of: date = Query(...), scenario: Scenario = Depends(get_scenario)):
        return json_response(reporting.executive_summary(scenario, as_of))

    @app.get("/scenarios/{scenario_id}/projection")
    def projection_endpoint(
        scenario_id: str,
        as_of: date = Query(...),
        retirement_date: date | None = None,
        terminal_age: int | None = None,
        scenario: Scenario = Depends(get_scenario),
    ):
        return json_response(
            reporting.annual_projection_table(
                scenario, as_of, retirement_date=retirement_date, terminal_age=terminal_age
            )
        )

    @app.post("/scenarios/{scenario_id}/clone", status_code=201)
    def clone_endpoint(scenario_id: str, body: CloneRequest, store: ScenarioStore = Depends(get_store)):
        get_scenario(scenario_id, store)  # 404s before the 409 check below if id is bad
        try:
            clone = store.clone(scenario_id, body.new_name)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return json_response({"id": clone.name, "parent_name": clone.parent_name}, status_code=201)

    @app.post("/reports")
    def reports_endpoint(body: ReportRequest, store: ScenarioStore = Depends(get_store)):
        scenario = get_scenario(body.scenario_id, store)
        builder = REPORT_BUILDERS.get(body.report_type)
        if builder is None:
            raise HTTPException(422, f"Unknown report_type {body.report_type!r}; choose one of {sorted(REPORT_BUILDERS)}")
        alternative = None
        if body.alternative_scenario_id is not None:
            alternative = get_scenario(body.alternative_scenario_id, store)
        if body.report_type == "scenario_comparison" and alternative is None:
            raise HTTPException(422, "scenario_comparison report_type requires alternative_scenario_id")
        report = builder(scenario, body.as_of, alternative)
        exporter = EXPORTERS.get(body.format)
        if exporter is None:
            raise HTTPException(422, f"Unknown format {body.format!r}; choose one of {sorted(EXPORTERS)}")
        export_fn, media_type = exporter
        return Response(content=export_fn(report), media_type=media_type)

    @app.get("/audit-events")
    def audit_events_endpoint(scenario_id: str | None = Query(None), store: ScenarioStore = Depends(get_store)):
        scenario_ids = [scenario_id] if scenario_id is not None else store.list_ids()
        events = [
            {"scenario_id": sid, "change": change}
            for sid in scenario_ids
            for change in get_scenario(sid, store).changes
        ]
        return json_response(events)

    return app


app = create_app()
