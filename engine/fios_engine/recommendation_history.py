"""Recommendation History (PRD Section 26.1, Phase 6b).

Section 26.1 requires recommendations be "persisted and queryable" with a validated
status lifecycle and, "where measurable," a realized impact computed later. This engine
has no database or API layer (see delivery-plan.md's repeated notes to that effect) --
building one is a real infrastructure decision this pass does not make. Instead,
`RecommendationStore` is a small, swappable persistence abstraction with two
implementations: `InMemoryRecommendationStore` (process-lifetime only) and
`JSONFileRecommendationStore` (durable across restarts via a single JSON file, no new
dependency). Both satisfy "persisted and queryable" at the fidelity this pure-Python
calculation engine can support; a real multi-user deployment would replace either with
a database-backed implementation behind the same interface -- exactly the "engine must
not depend on the database ORM" boundary Section 7 already establishes elsewhere.

`model_version`/`scenario_version` (Section 26.1) have no formal versioning system to
draw from yet (no release pipeline, no `Scenario` version counter), so `MODEL_VERSION`
is a flat constant bumped by hand per phase, and `scenario_version` is a content
fingerprint (a short hash of the scenario's own `changes` log) -- both flagged
engine-author choices, not a PRD-specified scheme.

Realized impact (Section 26.1: "realized impact where measurable") is only measurable
once a recommendation has actually been acted on (`ACCEPTED`/`COMPLETED`), and even then
this engine has no live account-data feed to compare against (Section 8's Integrations
phase, not built) -- so `compute_realized_impact` recomputes the *same* candidate action
against a caller-supplied, presumably-updated baseline scenario and diffs it against the
originally-recorded expected impact. That is "realized impact relative to the model,"
not "impact measured against observed real-world results" -- a real distinction, stated
here rather than blurred.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from .comparison import ScenarioComparison, diff_snapshots, snapshot
from .dashboard import compute_dashboard_summary
from .models import RecommendationHistoryEntry, RecommendationRecord, RecommendationStatus, Scenario
from .recommendation import Recommendation, RecommendationSet, build_candidate_scenario

MODEL_VERSION = "fios-engine-phase6b"
RECOMMENDATION_TTL_DAYS = 90  # engine-author assumption; not specified in the PRD

ALLOWED_TRANSITIONS: dict[RecommendationStatus, set[RecommendationStatus]] = {
    RecommendationStatus.ACTIVE: {
        RecommendationStatus.ACCEPTED,
        RecommendationStatus.DISMISSED,
        RecommendationStatus.SUPERSEDED,
        RecommendationStatus.EXPIRED,
    },
    RecommendationStatus.ACCEPTED: {RecommendationStatus.COMPLETED, RecommendationStatus.SUPERSEDED},
    RecommendationStatus.COMPLETED: set(),
    RecommendationStatus.DISMISSED: set(),
    RecommendationStatus.SUPERSEDED: set(),
    RecommendationStatus.EXPIRED: set(),
}


class InvalidTransitionError(ValueError):
    pass


def scenario_version(scenario: Scenario) -> str:
    fingerprint = "|".join(
        f"{c.field_path}:{c.old_value}->{c.new_value}" for c in scenario.changes
    )
    return hashlib.sha256(fingerprint.encode()).hexdigest()[:12]


def _serialize_expected_impact(recommendation: Recommendation) -> dict[str, object]:
    comparison = recommendation.comparison
    return {
        "woa_impact_months": comparison.woa_impact_months,
        "fid_after": comparison.alternative.evaluated_at.isoformat() if comparison.alternative.evaluated_at else None,
        "sas_impact_dollars": str(comparison.sas_impact_dollars) if comparison.sas_impact_dollars is not None else None,
        "freedom_margin_after": str(comparison.alternative.freedom_margin) if comparison.alternative.freedom_margin is not None else None,
        "success_probability_after": comparison.success_probability_after,
        "tax_impact": str(comparison.tax_impact) if comparison.tax_impact is not None else None,
        "liquidity_impact": str(comparison.liquidity_impact) if comparison.liquidity_impact is not None else None,
        "rrs_before": str(recommendation.rrs_before.overall_score),
        "rrs_after": str(recommendation.rrs_after.overall_score),
    }


class InMemoryRecommendationStore:
    def __init__(self) -> None:
        self._records: dict[str, RecommendationRecord] = {}
        self._history: dict[str, list[RecommendationHistoryEntry]] = {}

    def save(self, record: RecommendationRecord) -> None:
        self._records[record.id] = record
        self._history.setdefault(record.id, [])

    def get(self, recommendation_id: str) -> RecommendationRecord:
        return self._records[recommendation_id]

    def list_records(
        self, scenario_name: str | None = None, status: RecommendationStatus | None = None
    ) -> list[RecommendationRecord]:
        records = self._records.values()
        if scenario_name is not None:
            records = (r for r in records if r.scenario_name == scenario_name)
        if status is not None:
            records = (r for r in records if r.status is status)
        return sorted(records, key=lambda r: (r.created_at, r.id))

    def history_for(self, recommendation_id: str) -> list[RecommendationHistoryEntry]:
        return list(self._history.get(recommendation_id, []))

    def change_status(
        self,
        recommendation_id: str,
        new_status: RecommendationStatus,
        as_of: date,
        user_response: str | None = None,
    ) -> RecommendationHistoryEntry:
        record = self._records[recommendation_id]
        allowed = ALLOWED_TRANSITIONS[record.status]
        if new_status not in allowed:
            raise InvalidTransitionError(
                f"cannot transition recommendation {recommendation_id} from {record.status.value} "
                f"to {new_status.value}; allowed: {sorted(s.value for s in allowed) or 'none (terminal)'}"
            )
        entry = RecommendationHistoryEntry(
            recommendation_id=recommendation_id,
            timestamp=as_of,
            old_status=record.status,
            new_status=new_status,
            user_response=user_response,
        )
        self._records[recommendation_id] = replace(record, status=new_status)
        self._history.setdefault(recommendation_id, []).append(entry)
        return entry

    def record_realized_impact(
        self, recommendation_id: str, realized_impact: dict[str, object], as_of: date
    ) -> RecommendationHistoryEntry:
        record = self._records[recommendation_id]
        if record.status not in (RecommendationStatus.ACCEPTED, RecommendationStatus.COMPLETED):
            raise ValueError(
                f"recommendation {recommendation_id} is {record.status.value}; realized impact is only "
                "measurable once a recommendation has been accepted"
            )
        entry = RecommendationHistoryEntry(
            recommendation_id=recommendation_id,
            timestamp=as_of,
            old_status=record.status,
            new_status=record.status,
            realized_impact=realized_impact,
        )
        self._history.setdefault(recommendation_id, []).append(entry)
        return entry


class JSONFileRecommendationStore(InMemoryRecommendationStore):
    """Durable across process restarts: the full store state is written to `path` as
    JSON after every mutation. Not a database -- no concurrent-writer safety, no
    indexing beyond a linear scan -- but genuinely persisted, which an in-memory store
    is not, and requires no new dependency."""

    def __init__(self, path: Path | str) -> None:
        super().__init__()
        self._path = Path(path)
        if self._path.exists():
            self._load()

    def save(self, record: RecommendationRecord) -> None:
        super().save(record)
        self._flush()

    def change_status(self, *args, **kwargs) -> RecommendationHistoryEntry:
        entry = super().change_status(*args, **kwargs)
        self._flush()
        return entry

    def record_realized_impact(self, *args, **kwargs) -> RecommendationHistoryEntry:
        entry = super().record_realized_impact(*args, **kwargs)
        self._flush()
        return entry

    def _flush(self) -> None:
        payload = {
            "records": [_record_to_json(r) for r in self._records.values()],
            "history": {
                recommendation_id: [_entry_to_json(e) for e in entries]
                for recommendation_id, entries in self._history.items()
            },
        }
        self._path.write_text(json.dumps(payload, indent=2))

    def _load(self) -> None:
        payload = json.loads(self._path.read_text())
        for raw in payload.get("records", []):
            record = _record_from_json(raw)
            self._records[record.id] = record
        for recommendation_id, raw_entries in payload.get("history", {}).items():
            self._history[recommendation_id] = [_entry_from_json(e) for e in raw_entries]


def _record_to_json(record: RecommendationRecord) -> dict:
    data = asdict(record)
    data["created_at"] = record.created_at.isoformat()
    data["timing"] = record.timing.isoformat()
    data["amount"] = str(record.amount)
    data["confidence_score"] = str(record.confidence_score)
    data["decision_type"] = record.decision_type.value if record.decision_type is not None else None
    data["status"] = record.status.value
    return data


def _record_from_json(data: dict) -> RecommendationRecord:
    from .models import DecisionType

    data = dict(data)
    data["created_at"] = date.fromisoformat(data["created_at"])
    data["timing"] = date.fromisoformat(data["timing"])
    data["amount"] = Decimal(data["amount"])
    data["confidence_score"] = Decimal(data["confidence_score"])
    data["decision_type"] = DecisionType(data["decision_type"]) if data["decision_type"] is not None else None
    data["status"] = RecommendationStatus(data["status"])
    return RecommendationRecord(**data)


def _entry_to_json(entry: RecommendationHistoryEntry) -> dict:
    return {
        "recommendation_id": entry.recommendation_id,
        "timestamp": entry.timestamp.isoformat(),
        "old_status": entry.old_status.value if entry.old_status is not None else None,
        "new_status": entry.new_status.value,
        "user_response": entry.user_response,
        "realized_impact": entry.realized_impact,
    }


def _entry_from_json(data: dict) -> RecommendationHistoryEntry:
    return RecommendationHistoryEntry(
        recommendation_id=data["recommendation_id"],
        timestamp=date.fromisoformat(data["timestamp"]),
        old_status=RecommendationStatus(data["old_status"]) if data["old_status"] is not None else None,
        new_status=RecommendationStatus(data["new_status"]),
        user_response=data.get("user_response"),
        realized_impact=data.get("realized_impact"),
    )


def save_recommendation_set(
    store: InMemoryRecommendationStore,
    scenario: Scenario,
    recommendation_set: RecommendationSet,
    as_of: date,
) -> list[RecommendationRecord]:
    """Supersedes any still-Active records for this scenario (a fresh recommendation
    run replaces prior suggestions -- Section 26.1's `SUPERSEDED` status), then
    persists the new set as fresh `ACTIVE` records."""
    for existing in store.list_records(scenario_name=scenario.name, status=RecommendationStatus.ACTIVE):
        store.change_status(existing.id, RecommendationStatus.SUPERSEDED, as_of)

    version = scenario_version(scenario)
    records = []
    for recommendation in recommendation_set.recommendations:
        record = RecommendationRecord(
            id=uuid.uuid4().hex,
            scenario_name=scenario.name,
            created_at=as_of,
            model_version=MODEL_VERSION,
            scenario_version=version,
            action=recommendation.action,
            reason=recommendation.reason,
            decision_type=recommendation.decision_type,
            timing=recommendation.timing,
            amount=recommendation.amount,
            funding_source=recommendation.funding_source,
            confidence_level=recommendation.confidence_level,
            confidence_score=recommendation.confidence_score,
            invalidation_conditions=list(recommendation.invalidation_conditions),
            assumptions_snapshot=list(recommendation.assumptions),
            expected_impact=_serialize_expected_impact(recommendation),
        )
        store.save(record)
        records.append(record)
    return records


def expire_stale(
    store: InMemoryRecommendationStore, as_of: date, ttl_days: int = RECOMMENDATION_TTL_DAYS
) -> list[RecommendationHistoryEntry]:
    entries = []
    for record in store.list_records(status=RecommendationStatus.ACTIVE):
        if as_of - record.created_at >= timedelta(days=ttl_days):
            entries.append(store.change_status(record.id, RecommendationStatus.EXPIRED, as_of))
    return entries


def compute_realized_impact(
    record: RecommendationRecord, current_baseline: Scenario
) -> ScenarioComparison | None:
    """`None` if the recommendation hasn't been acted on yet (nothing to measure).
    Otherwise rebuilds the same candidate action (via
    `recommendation.build_candidate_scenario`, keyed by the kind recovered from the
    stored action label) against `current_baseline` and diffs it the same way the
    original recommendation was evaluated -- see the module docstring for why this is
    "realized relative to the model," not relative to observed real-world results."""
    if record.status not in (RecommendationStatus.ACCEPTED, RecommendationStatus.COMPLETED):
        return None

    kind = _kind_from_action(record.action)
    candidate_scenario = build_candidate_scenario(
        current_baseline, kind, record.timing, record.amount, record.funding_source
    )

    baseline_summary = compute_dashboard_summary(current_baseline)
    baseline_snapshot = snapshot(current_baseline, summary=baseline_summary)
    candidate_summary = compute_dashboard_summary(candidate_scenario)
    if not candidate_summary.woa.achievable:
        return None
    candidate_snapshot = snapshot(candidate_scenario, summary=candidate_summary)

    return diff_snapshots(
        baseline_snapshot,
        candidate_snapshot,
        current_baseline.monte_carlo_enabled,
        candidate_scenario.monte_carlo_enabled,
    )


def _kind_from_action(action: str) -> str:
    """Recommendations/records don't carry `CandidateAction.kind` directly (it isn't
    part of the Section 26 output-field set), so it is recovered from `action`'s label
    -- a small, explicit mapping, not string-sniffing arbitrary text, since the label
    set is fixed and enumerated in `recommendation._generate_candidates`."""
    if action.startswith("Convert $"):
        return "roth_conversion"
    if action.startswith("Reduce discretionary spending"):
        return "discretionary_cut"
    if action == "Switch to proportional withdrawals across accounts":
        return "proportional_withdrawal"
    if action.startswith("Purchase additional real estate"):
        return "real_estate_purchase"
    if action == "Emergency lake-home sale":
        return "real_estate_sale"
    raise ValueError(f"cannot determine candidate kind for recommendation action: {action!r}")
