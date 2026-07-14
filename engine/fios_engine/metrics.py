"""Net worth, investable assets, and related balance-sheet metrics (PRD Section 5, 25)."""

from __future__ import annotations

from decimal import Decimal


def total_assets(
    account_balances: dict[str, Decimal], equity_value: Decimal, real_estate_value: Decimal
) -> Decimal:
    return sum(account_balances.values(), Decimal("0")) + equity_value + real_estate_value


def net_worth(assets: Decimal, liabilities: Decimal) -> Decimal:
    return assets - liabilities


def investable_assets(account_balances: dict[str, Decimal], equity_value: Decimal) -> Decimal:
    """Cash, taxable, retirement accounts, and liquidated company equity. Excludes
    personal-use real estate (Section 5)."""
    return sum(account_balances.values(), Decimal("0")) + equity_value
