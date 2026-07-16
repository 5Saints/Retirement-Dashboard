"""Tests for the scenario clone/override primitive (Section 8)."""

from decimal import Decimal

from fios_engine.scenario_engine import clone_scenario, record_change
from fios_engine.seed import build_baseline_scenario


def test_clone_is_independent_of_parent():
    parent = build_baseline_scenario()

    clone = clone_scenario(parent, "Clone")
    clone.household.accounts["taxable"].opening_balance = Decimal("999999")
    clone.retirement_inflation_rate = Decimal("0.99")

    assert parent.household.accounts["taxable"].opening_balance == Decimal("400000")
    assert parent.retirement_inflation_rate == Decimal("0.03")


def test_clone_records_lineage_and_starts_with_no_changes():
    parent = build_baseline_scenario()

    clone = clone_scenario(parent, "Clone")

    assert clone.name == "Clone"
    assert clone.parent_name == "Baseline"
    assert clone.changes == []
    assert parent.parent_name is None


def test_record_change_appends_audit_entry():
    parent = build_baseline_scenario()
    clone = clone_scenario(parent, "Clone")

    record_change(clone, "household.planned_retirement_age", 59, 57, "test", "unit test")

    assert len(clone.changes) == 1
    change = clone.changes[0]
    assert change.old_value == 59
    assert change.new_value == 57
    assert change.source == "test"
    assert parent.changes == []
