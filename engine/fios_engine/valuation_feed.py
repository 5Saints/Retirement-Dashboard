"""External valuation feeds (PRD Section 8/21 Phase 8; Section 3.2).

Section 3.2 explicitly lists "Live brokerage aggregation" under "Deferred or Optional" --
a real vendor connection (Plaid/Yodlee/MX-style OAuth aggregation) is out of scope for
this engine and stays deferred. What this module implements instead is the part of
Phase 8 that fits inside a pure, dependency-free calculation library: a small
`AccountSnapshot` record, CSV/JSON parsers that turn externally-supplied account
balances into snapshots, and `apply_valuation_feed` to fold them into a *cloned*
Scenario with a full Section 28 audit trail -- the same clone-then-record pattern every
`scenario_library` builder already uses.

There is no live network call, no OAuth flow, and no credential of any kind anywhere in
this module -- Section 15's "do not store account passwords or brokerage credentials in
application tables" is satisfied trivially because this module never sees any. A caller
is expected to have already obtained balances by some out-of-band means (a user typing
them in, a manually exported CSV from their brokerage) and hands them to this module as
plain data.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .models import Scenario, Status
from .scenario_engine import clone_scenario, record_change


@dataclass(frozen=True)
class AccountSnapshot:
    account_name: str
    balance: Decimal
    as_of: date
    source: str
    status: Status = Status.CONFIRMED


def parse_csv_snapshots(text: str, source: str, status: Status = Status.CONFIRMED) -> list[AccountSnapshot]:
    """Expects a header row with `account_name`, `balance`, `as_of` (ISO 8601 date)."""
    reader = csv.DictReader(io.StringIO(text))
    return [
        AccountSnapshot(
            account_name=row["account_name"],
            balance=Decimal(row["balance"]),
            as_of=date.fromisoformat(row["as_of"]),
            source=source,
            status=status,
        )
        for row in reader
    ]


def parse_json_snapshots(text: str, source: str, status: Status = Status.CONFIRMED) -> list[AccountSnapshot]:
    """Expects a JSON list of objects with `account_name`, `balance`, `as_of` (ISO 8601
    date) keys."""
    records = json.loads(text)
    return [
        AccountSnapshot(
            account_name=record["account_name"],
            balance=Decimal(str(record["balance"])),
            as_of=date.fromisoformat(record["as_of"]),
            source=source,
            status=status,
        )
        for record in records
    ]


def _latest_per_account(snapshots: list[AccountSnapshot]) -> dict[str, AccountSnapshot]:
    latest: dict[str, AccountSnapshot] = {}
    for snapshot in snapshots:
        current = latest.get(snapshot.account_name)
        if current is None or snapshot.as_of > current.as_of:
            latest[snapshot.account_name] = snapshot
    return latest


def apply_valuation_feed(baseline: Scenario, snapshots: list[AccountSnapshot], scenario_name: str) -> Scenario:
    """Clones `baseline` (Section 8's clone-before-edit convention) and overwrites each
    named account's `opening_balance` with its latest snapshot, recording one Section 28
    `AssumptionChange` per updated account. Raises `ValueError` naming any snapshot
    account that doesn't exist on the household -- Section 18's "never silently
    defaulted" extends to a typo'd or unrecognized account name in an external feed, not
    just an unspecified engine parameter. A feed covering only a subset of the
    household's accounts is expected, not an error -- accounts absent from `snapshots`
    are left untouched. When `snapshots` names the same account more than once (e.g. a
    feed spanning several as-of dates), the latest `as_of` wins."""
    unknown = {snapshot.account_name for snapshot in snapshots} - set(baseline.household.accounts)
    if unknown:
        raise ValueError(f"Valuation feed references unknown account(s): {sorted(unknown)}")

    updated = clone_scenario(baseline, scenario_name)
    for account_name, snapshot in _latest_per_account(snapshots).items():
        account = updated.household.accounts[account_name]
        old_balance = account.opening_balance
        account.opening_balance = snapshot.balance
        record_change(
            updated,
            field_path=f"accounts.{account_name}.opening_balance",
            old_value=old_balance,
            new_value=snapshot.balance,
            source=snapshot.source,
            reason=f"Applied external valuation feed snapshot as of {snapshot.as_of}",
            effective_date=snapshot.as_of,
        )
    return updated
