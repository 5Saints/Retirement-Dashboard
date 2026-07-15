"""Tests for the Recommendation History store (Section 26.1, Phase 6b)."""

from datetime import date, timedelta

import pytest

from fios_engine.models import RecommendationStatus
from fios_engine.recommendation import generate_recommendations
from fios_engine.recommendation_history import (
    ALLOWED_TRANSITIONS,
    InMemoryRecommendationStore,
    InvalidTransitionError,
    JSONFileRecommendationStore,
    compute_realized_impact,
    expire_stale,
    save_recommendation_set,
)
from fios_engine.seed import build_baseline_scenario

TODAY = date(2026, 7, 15)


@pytest.fixture(scope="module")
def fast_scenario():
    scenario = build_baseline_scenario()
    scenario.monte_carlo_enabled = False
    return scenario


@pytest.fixture(scope="module")
def recommendation_set(fast_scenario):
    return generate_recommendations(fast_scenario)


def test_save_recommendation_set_creates_active_records(fast_scenario, recommendation_set):
    store = InMemoryRecommendationStore()

    records = save_recommendation_set(store, fast_scenario, recommendation_set, TODAY)

    assert len(records) == len(recommendation_set.recommendations)
    for record in records:
        assert record.status is RecommendationStatus.ACTIVE
        assert record.scenario_name == fast_scenario.name
        assert record.created_at == TODAY
        assert store.get(record.id) == record


def test_list_records_filters_by_scenario_and_status(fast_scenario, recommendation_set):
    store = InMemoryRecommendationStore()
    save_recommendation_set(store, fast_scenario, recommendation_set, TODAY)

    active = store.list_records(scenario_name=fast_scenario.name, status=RecommendationStatus.ACTIVE)
    other_scenario = store.list_records(scenario_name="Some other scenario")

    assert len(active) == len(recommendation_set.recommendations)
    assert other_scenario == []


def test_valid_status_transition_succeeds_and_is_recorded(fast_scenario, recommendation_set):
    store = InMemoryRecommendationStore()
    records = save_recommendation_set(store, fast_scenario, recommendation_set, TODAY)
    record_id = records[0].id

    entry = store.change_status(record_id, RecommendationStatus.ACCEPTED, TODAY)

    assert store.get(record_id).status is RecommendationStatus.ACCEPTED
    assert entry.old_status is RecommendationStatus.ACTIVE
    assert entry.new_status is RecommendationStatus.ACCEPTED
    assert store.history_for(record_id) == [entry]


def test_invalid_status_transition_raises(fast_scenario, recommendation_set):
    store = InMemoryRecommendationStore()
    records = save_recommendation_set(store, fast_scenario, recommendation_set, TODAY)
    record_id = records[0].id
    store.change_status(record_id, RecommendationStatus.ACCEPTED, TODAY)

    with pytest.raises(InvalidTransitionError):
        store.change_status(record_id, RecommendationStatus.DISMISSED, TODAY)


@pytest.mark.parametrize(
    "terminal_status",
    [
        RecommendationStatus.COMPLETED,
        RecommendationStatus.DISMISSED,
        RecommendationStatus.SUPERSEDED,
        RecommendationStatus.EXPIRED,
    ],
)
def test_terminal_statuses_allow_no_further_transitions(terminal_status):
    assert ALLOWED_TRANSITIONS[terminal_status] == set()


def test_realized_impact_is_none_before_acceptance(fast_scenario, recommendation_set):
    store = InMemoryRecommendationStore()
    records = save_recommendation_set(store, fast_scenario, recommendation_set, TODAY)

    result = compute_realized_impact(records[0], fast_scenario)

    assert result is None


def test_recording_realized_impact_requires_accepted_status(fast_scenario, recommendation_set):
    store = InMemoryRecommendationStore()
    records = save_recommendation_set(store, fast_scenario, recommendation_set, TODAY)

    with pytest.raises(ValueError):
        store.record_realized_impact(records[0].id, {"note": "too early"}, TODAY)


def test_realized_impact_matches_expected_when_baseline_is_unchanged(fast_scenario, recommendation_set):
    store = InMemoryRecommendationStore()
    records = save_recommendation_set(store, fast_scenario, recommendation_set, TODAY)
    record = records[0]
    store.change_status(record.id, RecommendationStatus.ACCEPTED, TODAY)

    realized = compute_realized_impact(store.get(record.id), fast_scenario)

    assert realized is not None
    assert realized.woa_impact_months == record.expected_impact["woa_impact_months"]


def test_resaving_supersedes_only_still_active_records(fast_scenario, recommendation_set):
    store = InMemoryRecommendationStore()
    records = save_recommendation_set(store, fast_scenario, recommendation_set, TODAY)
    accepted_id = records[0].id
    store.change_status(accepted_id, RecommendationStatus.ACCEPTED, TODAY)

    save_recommendation_set(store, fast_scenario, recommendation_set, TODAY + timedelta(days=1))

    assert store.get(accepted_id).status is RecommendationStatus.ACCEPTED
    superseded = store.list_records(scenario_name=fast_scenario.name, status=RecommendationStatus.SUPERSEDED)
    assert len(superseded) == len(records) - 1


def test_expire_stale_transitions_old_active_records(fast_scenario, recommendation_set):
    store = InMemoryRecommendationStore()
    save_recommendation_set(store, fast_scenario, recommendation_set, TODAY)

    entries = expire_stale(store, TODAY + timedelta(days=200))

    assert len(entries) == len(recommendation_set.recommendations)
    assert store.list_records(status=RecommendationStatus.ACTIVE) == []
    assert len(store.list_records(status=RecommendationStatus.EXPIRED)) == len(recommendation_set.recommendations)


def test_expire_stale_leaves_recent_records_active(fast_scenario, recommendation_set):
    store = InMemoryRecommendationStore()
    save_recommendation_set(store, fast_scenario, recommendation_set, TODAY)

    entries = expire_stale(store, TODAY + timedelta(days=1))

    assert entries == []
    assert len(store.list_records(status=RecommendationStatus.ACTIVE)) == len(recommendation_set.recommendations)


def test_json_file_store_persists_across_instances(tmp_path, fast_scenario, recommendation_set):
    path = tmp_path / "recommendations.json"
    store = JSONFileRecommendationStore(path)
    records = save_recommendation_set(store, fast_scenario, recommendation_set, TODAY)
    store.change_status(records[0].id, RecommendationStatus.ACCEPTED, TODAY)

    assert path.exists()

    reloaded = JSONFileRecommendationStore(path)

    assert len(reloaded.list_records()) == len(records)
    assert reloaded.get(records[0].id).status is RecommendationStatus.ACCEPTED
    assert reloaded.get(records[0].id).amount == records[0].amount
    assert reloaded.get(records[0].id).invalidation_conditions == records[0].invalidation_conditions
    assert len(reloaded.history_for(records[0].id)) == 1
