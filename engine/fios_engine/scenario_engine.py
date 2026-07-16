"""Scenario clone/override primitive (PRD Section 8: "A scenario is a complete,
immutable set of assumptions derived from a parent scenario").

`clone_scenario` is the one general-purpose operation this module provides: a deep
copy detached from its parent, ready for a caller (a `scenario_library` builder, a
one-off decision, a test) to mutate freely. It does not itself interpret "what changed"
-- callers append `AssumptionChange` records themselves via `record_change`, since only
the caller making a specific edit knows the field path, old value, and reason for it.
This mirrors how the Section 11 `ScenarioOverride`/`AuditEvent` entities are meant to be
populated by whatever layer makes the edit, not inferred generically after the fact.
"""

from __future__ import annotations

import copy
from datetime import date
from typing import Any

from .models import AssumptionChange, Scenario


def clone_scenario(parent: Scenario, name: str) -> Scenario:
    """Deep-copy `parent` into an independent scenario named `name`, with `parent_name`
    set to `parent.name` and an empty change log. `parent` itself is never mutated."""
    clone = copy.deepcopy(parent)
    clone.name = name
    clone.parent_name = parent.name
    clone.changes = []
    return clone


def record_change(
    scenario: Scenario,
    field_path: str,
    old_value: Any,
    new_value: Any,
    source: str,
    reason: str,
    effective_date: date | None = None,
) -> None:
    """Append an audit-trail entry (Section 28) to `scenario.changes` in place."""
    scenario.changes.append(
        AssumptionChange(
            field_path=field_path,
            old_value=old_value,
            new_value=new_value,
            source=source,
            reason=reason,
            effective_date=effective_date,
        )
    )
