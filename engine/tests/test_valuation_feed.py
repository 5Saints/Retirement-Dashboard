"""Tests for external valuation feeds (Section 8/21 Phase 8; Section 3.2)."""

from datetime import date
from decimal import Decimal

import pytest

from fios_engine.models import Status
from fios_engine.seed import build_baseline_scenario
from fios_engine.valuation_feed import (
    AccountSnapshot,
    apply_valuation_feed,
    parse_csv_snapshots,
    parse_json_snapshots,
)


def test_parse_csv_snapshots_reads_the_expected_columns():
    text = "account_name,balance,as_of\ncash,150000.00,2026-07-01\n401k,900000,2026-07-01\n"

    snapshots = parse_csv_snapshots(text, source="manual_csv_import")

    assert snapshots == [
        AccountSnapshot("cash", Decimal("150000.00"), date(2026, 7, 1), "manual_csv_import"),
        AccountSnapshot("401k", Decimal("900000"), date(2026, 7, 1), "manual_csv_import"),
    ]


def test_parse_json_snapshots_reads_the_expected_fields():
    text = '[{"account_name": "cash", "balance": 150000, "as_of": "2026-07-01"}]'

    snapshots = parse_json_snapshots(text, source="manual_json_import", status=Status.ESTIMATED)

    assert snapshots == [
        AccountSnapshot("cash", Decimal("150000"), date(2026, 7, 1), "manual_json_import", Status.ESTIMATED)
    ]


def test_apply_valuation_feed_updates_only_the_named_account():
    baseline = build_baseline_scenario()
    original_401k = baseline.household.accounts["401k"].opening_balance
    snapshots = [AccountSnapshot("cash", Decimal("150000.00"), date(2026, 7, 1), "manual_csv_import")]

    updated = apply_valuation_feed(baseline, snapshots, "With live balance")

    assert updated.household.accounts["cash"].opening_balance == Decimal("150000.00")
    assert updated.household.accounts["401k"].opening_balance == original_401k


def test_apply_valuation_feed_does_not_mutate_the_baseline():
    baseline = build_baseline_scenario()
    original_cash = baseline.household.accounts["cash"].opening_balance
    snapshots = [AccountSnapshot("cash", Decimal("999999"), date(2026, 7, 1), "manual_csv_import")]

    apply_valuation_feed(baseline, snapshots, "With live balance")

    assert baseline.household.accounts["cash"].opening_balance == original_cash


def test_apply_valuation_feed_records_an_assumption_change_per_updated_account():
    baseline = build_baseline_scenario()
    snapshots = [
        AccountSnapshot("cash", Decimal("150000.00"), date(2026, 7, 1), "manual_csv_import"),
        AccountSnapshot("401k", Decimal("900000"), date(2026, 7, 1), "manual_csv_import"),
    ]

    updated = apply_valuation_feed(baseline, snapshots, "With live balances")

    assert len(updated.changes) == 2
    fields = {change.field_path for change in updated.changes}
    assert fields == {"accounts.cash.opening_balance", "accounts.401k.opening_balance"}
    assert updated.changes[0].source == "manual_csv_import"
    assert updated.changes[0].effective_date == date(2026, 7, 1)


def test_apply_valuation_feed_rejects_an_unknown_account_name():
    baseline = build_baseline_scenario()
    snapshots = [AccountSnapshot("brokerage_xyz", Decimal("1"), date(2026, 7, 1), "manual_csv_import")]

    with pytest.raises(ValueError, match="brokerage_xyz"):
        apply_valuation_feed(baseline, snapshots, "Bad feed")


def test_apply_valuation_feed_uses_the_latest_snapshot_when_an_account_repeats():
    baseline = build_baseline_scenario()
    snapshots = [
        AccountSnapshot("cash", Decimal("100000.00"), date(2026, 1, 1), "manual_csv_import"),
        AccountSnapshot("cash", Decimal("200000.00"), date(2026, 7, 1), "manual_csv_import"),
    ]

    updated = apply_valuation_feed(baseline, snapshots, "With repeated snapshots")

    assert updated.household.accounts["cash"].opening_balance == Decimal("200000.00")
    assert len(updated.changes) == 1


def test_apply_valuation_feed_leaves_the_scenario_unchanged_when_snapshots_is_empty():
    baseline = build_baseline_scenario()

    updated = apply_valuation_feed(baseline, [], "No-op feed")

    assert updated.changes == []
    for name, account in updated.household.accounts.items():
        assert account.opening_balance == baseline.household.accounts[name].opening_balance
