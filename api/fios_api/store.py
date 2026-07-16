"""In-memory scenario store (PRD Section 16/21 Phase 8+ API layer -- minimal scope).

Section 16 recommends a PostgreSQL-backed persistence layer for `Household`/`Scenario`/
`ProjectionResult` entities; that layer does not exist yet. This store is an explicit,
documented stand-in -- the same role `recommendation_history.InMemoryRecommendationStore`
plays for recommendations. State lives only for the lifetime of the process (or, more
precisely here, of one `ScenarioStore` instance): a fresh instance starts back at the
seeded baseline plus a couple of built-in scenario-library variants, ready to explore. No
multi-user isolation and no auth exist anywhere in this module (Section 15 is entirely
unaddressed) -- this is a local single-user prototype layer, not a production
deployment.
"""

from __future__ import annotations

from fios_engine import scenario_library as lib
from fios_engine.models import Scenario
from fios_engine.scenario_engine import clone_scenario
from fios_engine.seed import build_baseline_scenario


def _seed_scenarios() -> dict[str, Scenario]:
    baseline = build_baseline_scenario()
    return {
        scenario.name: scenario
        for scenario in (
            baseline,
            lib.conservative_returns(baseline),
            lib.optimistic_returns(baseline),
        )
    }


class ScenarioStore:
    def __init__(self) -> None:
        self._scenarios: dict[str, Scenario] = _seed_scenarios()

    def list_ids(self) -> list[str]:
        return list(self._scenarios)

    def get(self, scenario_id: str) -> Scenario:
        try:
            return self._scenarios[scenario_id]
        except KeyError:
            raise KeyError(f"No scenario named {scenario_id!r}") from None

    def put(self, scenario: Scenario) -> None:
        self._scenarios[scenario.name] = scenario

    def clone(self, scenario_id: str, new_name: str) -> Scenario:
        """Section 12: "Users must be able to clone a scenario before editing." This is
        a plain duplicate under a new name -- applying a specific assumption change
        (e.g. a built-in scenario-library variant, a Decision) is a separate concern
        handled by the endpoints that need it (`/decisions/evaluate`), not by this
        generic clone primitive."""
        if new_name in self._scenarios:
            raise ValueError(f"A scenario named {new_name!r} already exists")
        clone = clone_scenario(self.get(scenario_id), new_name)
        self.put(clone)
        return clone
