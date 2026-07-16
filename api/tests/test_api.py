"""Tests for the minimal FastAPI layer (PRD Section 16/17.1; Phase 8+ scope).

Each test gets a fresh `create_app()`/`ScenarioStore` -- no shared module-level state
between tests, since several tests mutate the store (clone, decisions/evaluate).
"""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from fios_api.main import create_app

AS_OF = "2026-07-16"


@pytest.fixture
def client():
    return TestClient(create_app())


def test_list_scenarios_includes_the_seeded_baseline_and_variants(client):
    response = client.get("/scenarios")

    assert response.status_code == 200
    ids = {row["id"] for row in response.json()}
    assert ids == {"Baseline", "Conservative returns", "Optimistic returns"}


def test_calculate_returns_woa_sas_rrs_and_legacy_as_exact_decimal_strings(client):
    response = client.post("/scenarios/Baseline/calculate")

    assert response.status_code == 200
    body = response.json()
    assert body["fid"] is not None
    assert body["sas"] is not None
    # Every Decimal in the payload round-trips as an exact string, never a float.
    sustainable_spending = body["sas"]["sustainable_spending"]
    assert isinstance(sustainable_spending, str)
    Decimal(sustainable_spending)  # does not raise
    assert isinstance(body["retirement_readiness_score"]["overall_score"], str)


def test_calculate_404s_for_an_unknown_scenario(client):
    response = client.post("/scenarios/does-not-exist/calculate")

    assert response.status_code == 404


def test_monte_carlo_runs_with_an_explicit_retirement_date_and_simulation_count(client):
    response = client.post(
        "/scenarios/Baseline/monte-carlo",
        json={"retirement_date": "2032-01-01", "num_simulations": 200, "seed": 1},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["num_simulations"] == 200
    assert body["seed"] == 1
    assert 0.0 <= body["success_probability"] <= 1.0


def test_dashboard_returns_the_executive_summary_report(client):
    response = client.get("/scenarios/Baseline/dashboard", params={"as_of": AS_OF})

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Executive Summary"
    assert body["metadata"]["scenario_name"] == "Baseline"
    metric_names = {row["metric"] for row in body["sections"][0]["rows"]}
    assert "Work-Optional Age / FID" in metric_names


def test_dashboard_requires_as_of(client):
    response = client.get("/scenarios/Baseline/dashboard")

    assert response.status_code == 422


def test_projection_returns_one_row_per_year(client):
    response = client.get("/scenarios/Baseline/projection", params={"as_of": AS_OF})

    assert response.status_code == 200
    rows = response.json()["sections"][0]["rows"]
    years = [row["year"] for row in rows]
    assert years == sorted(years)
    assert len(years) == len(set(years))


def test_clone_creates_a_new_scenario_visible_in_the_list(client):
    response = client.post("/scenarios/Baseline/clone", json={"new_name": "My Clone"})

    assert response.status_code == 201
    assert response.json() == {"id": "My Clone", "parent_name": "Baseline"}
    ids = {row["id"] for row in client.get("/scenarios").json()}
    assert "My Clone" in ids


def test_clone_with_a_duplicate_name_is_a_conflict(client):
    client.post("/scenarios/Baseline/clone", json={"new_name": "Dup"})

    response = client.post("/scenarios/Baseline/clone", json={"new_name": "Dup"})

    assert response.status_code == 409


def test_clone_of_an_unknown_scenario_404s(client):
    response = client.post("/scenarios/does-not-exist/clone", json={"new_name": "x"})

    assert response.status_code == 404


def test_decisions_evaluate_returns_a_comparison_and_what_changed(client):
    response = client.post(
        "/scenarios/Baseline/decisions/evaluate",
        json={
            "decision_type": "roth_conversion",
            "effective_date": "2032-06-01",
            "amount": "50000",
            "funding_source": "cash",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert "woa_impact_months" in body["comparison"]
    assert isinstance(body["what_changed"], list)
    assert len(body["what_changed"]) > 0


def test_decisions_evaluate_does_not_mutate_the_stored_baseline(client):
    before = client.get("/scenarios").json()

    client.post(
        "/scenarios/Baseline/decisions/evaluate",
        json={
            "decision_type": "roth_conversion",
            "effective_date": "2032-06-01",
            "amount": "50000",
            "funding_source": "cash",
        },
    )

    after = client.get("/scenarios").json()
    assert before == after


def test_decisions_evaluate_with_an_unknown_funding_source_is_a_client_error_not_a_500(client):
    response = client.post(
        "/scenarios/Baseline/decisions/evaluate",
        json={
            "decision_type": "roth_conversion",
            "effective_date": "2032-06-01",
            "amount": "50000",
            "funding_source": "not_a_real_account",
        },
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "fmt,content_type",
    [
        ("json", "application/json"),
        ("csv", "text/csv"),
        ("excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("pdf", "application/pdf"),
    ],
)
def test_reports_endpoint_produces_every_export_format(client, fmt, content_type):
    response = client.post(
        "/reports",
        json={"scenario_id": "Baseline", "report_type": "assumption_register", "format": fmt, "as_of": AS_OF},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(content_type)
    assert len(response.content) > 0


def test_reports_endpoint_covers_all_twelve_section_14_report_types(client):
    from fios_api.main import REPORT_BUILDERS

    assert len(REPORT_BUILDERS) == 12
    for report_type in REPORT_BUILDERS:
        alt = "Conservative returns" if report_type == "scenario_comparison" else None
        payload = {"scenario_id": "Baseline", "report_type": report_type, "format": "json", "as_of": AS_OF}
        if alt is not None:
            payload["alternative_scenario_id"] = alt
        response = client.post("/reports", json=payload)
        assert response.status_code == 200, report_type


def test_reports_endpoint_rejects_an_unknown_report_type(client):
    response = client.post(
        "/reports", json={"scenario_id": "Baseline", "report_type": "bogus", "format": "json", "as_of": AS_OF}
    )

    assert response.status_code == 422


def test_reports_endpoint_rejects_an_unknown_format(client):
    response = client.post(
        "/reports",
        json={"scenario_id": "Baseline", "report_type": "executive_summary", "format": "bogus", "as_of": AS_OF},
    )

    assert response.status_code == 422


def test_scenario_comparison_report_requires_an_alternative_scenario_id(client):
    response = client.post(
        "/reports",
        json={"scenario_id": "Baseline", "report_type": "scenario_comparison", "format": "json", "as_of": AS_OF},
    )

    assert response.status_code == 422


def test_audit_events_returns_changes_recorded_on_built_in_scenario_variants(client):
    response = client.get("/audit-events")

    assert response.status_code == 200
    events = response.json()
    scenario_ids = {event["scenario_id"] for event in events}
    assert "Conservative returns" in scenario_ids
    assert all("change" in event for event in events)


def test_audit_events_can_be_filtered_by_scenario_id(client):
    response = client.get("/audit-events", params={"scenario_id": "Baseline"})

    assert response.status_code == 200
    assert response.json() == []  # the baseline itself has no recorded changes


def test_stores_are_isolated_across_separate_app_instances():
    """Each `create_app()` gets its own `ScenarioStore` -- a clone in one client must
    not leak into a client backed by a different app instance."""
    from fios_api.main import create_app as make_app

    client_a = TestClient(make_app())
    client_b = TestClient(make_app())

    client_a.post("/scenarios/Baseline/clone", json={"new_name": "Only in A"})

    ids_a = {row["id"] for row in client_a.get("/scenarios").json()}
    ids_b = {row["id"] for row in client_b.get("/scenarios").json()}
    assert "Only in A" in ids_a
    assert "Only in A" not in ids_b
