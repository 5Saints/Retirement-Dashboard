"""Baseline household seed data, exactly per PRD Section 4 and Appendix A.

This is production seed data, not a test fixture -- every value here is either Confirmed
or an explicitly flagged Assumption/Placeholder, matching the PRD's status column.

One exception: the `"roth"` account has no basis in Section 4/Appendix A (the baseline
household is not stated to hold any Roth savings) and is added at a $0 opening balance
purely so Section 7.5's Roth-conversion/withdrawal-order mechanics
(`models.DecisionType.ROTH_CONVERSION`, `Scenario.withdrawal_order`) are usable and
testable against the baseline household. A $0 balance has no effect on any Section 19
acceptance number.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from .models import (
    Account,
    DateMode,
    EquityPosition,
    ExpenseCategory,
    Household,
    IncomeStream,
    InterpolationMode,
    Liability,
    LiquidityEvent,
    PricePathAnchor,
    RealEstate,
    Scenario,
    Status,
    Valued,
)
from .tax import LIQUIDITY_EVENT_TAX_RATE

BASELINE_CURRENT_DATE = date(2026, 1, 1)
BASELINE_CURRENT_AGE = 53
BASELINE_RETIREMENT_AGE = 59  # retirement year 2032
BASELINE_TERMINAL_AGE = 100  # Section 4.1: age 95 minimum; model through age 100


def build_equity_position() -> EquityPosition:
    return EquityPosition(
        description="Private company equity",
        share_quantity=Decimal("166.122"),
        basis=None,
        anchors=[
            PricePathAnchor(date(2026, 1, 1), Decimal("21589.92"), Status.CONFIRMED),
            PricePathAnchor(date(2030, 1, 1), Decimal("70000"), Status.ASSUMPTION, "low confidence"),
        ],
        interpolation_mode=InterpolationMode.STEP,
    )


def build_liquidity_events(equity_position: EquityPosition) -> list[LiquidityEvent]:
    event_1 = LiquidityEvent(
        equity_position=equity_position,
        date_mode=DateMode.FIXED,
        shares_sold=Decimal("111.163"),
        tax_rate=LIQUIDITY_EVENT_TAX_RATE,
        fixed_date=date(2026, 9, 30),  # placeholder pending exact day (CL-1)
        real_estate_allocation=Decimal("500000"),
    )
    event_2 = LiquidityEvent(
        equity_position=equity_position,
        date_mode=DateMode.RETIREMENT_LINKED,
        shares_sold=Decimal("54.959"),
        tax_rate=LIQUIDITY_EVENT_TAX_RATE,
        real_estate_allocation=Decimal("0"),
    )
    return [event_1, event_2]


def build_baseline_household() -> Household:
    equity_position = build_equity_position()
    liquidity_events = build_liquidity_events(equity_position)

    accounts = {
        "cash": Account(
            name="Cash and cash equivalents",
            tax_treatment="cash",
            opening_balance=Decimal("100000"),
            annual_return=Valued(Decimal("0"), Status.CONFIRMED),
            liquidity_class="immediate",
        ),
        "401k": Account(
            name="401(k)",
            tax_treatment="tax_deferred",
            opening_balance=Decimal("575000"),
            annual_return=Valued(Decimal("0.06"), Status.ASSUMPTION),
            liquidity_class="retirement_restricted",
        ),
        "taxable": Account(
            name="Taxable brokerage",
            tax_treatment="taxable",
            opening_balance=Decimal("400000"),
            annual_return=Valued(Decimal("0.06"), Status.ASSUMPTION),
            liquidity_class="liquid",
        ),
        "roth": Account(
            name="Roth IRA",
            tax_treatment="roth",
            opening_balance=Decimal("0"),
            annual_return=Valued(Decimal("0.06"), Status.ASSUMPTION),
            liquidity_class="retirement_restricted",
        ),
    }

    liabilities = {
        "primary_mortgage": Liability(
            name="Primary residence mortgage",
            opening_balance=Decimal("100000"),
            payoff_boundary_date=date(2031, 12, 31),
        ),
        "lake_home_mortgage": Liability(
            name="Lake-home mortgage",
            opening_balance=Decimal("0"),
        ),
    }

    income_streams = [
        IncomeStream(
            name="Salary",
            annual_amount=Decimal("312000"),
            growth_rate=Decimal("0.02"),
            start_date=BASELINE_CURRENT_DATE,
        ),
        IncomeStream(
            name="Annual bonus",
            annual_amount=Decimal("100000"),
            growth_rate=Decimal("0"),
            start_date=BASELINE_CURRENT_DATE,
        ),
    ]

    expense_categories = [
        ExpenseCategory("Core living expenses", essential=True, anchor_amount=Decimal("150000")),
        ExpenseCategory("Travel", essential=False, anchor_amount=Decimal("40000")),
        ExpenseCategory("Vehicles", essential=False, anchor_amount=Decimal("20000")),
        ExpenseCategory("Hobbies", essential=False, anchor_amount=Decimal("20000")),
        ExpenseCategory("Home improvements", essential=False, anchor_amount=Decimal("30000")),
        ExpenseCategory("Miscellaneous", essential=False, anchor_amount=Decimal("40000")),
    ]

    real_estate = [
        RealEstate(
            name="Primary residence",
            value=Decimal("700000"),
            debt=Decimal("100000"),
            liquidity_role="residence",
        ),
        RealEstate(
            name="Lake home",
            value=Decimal("1500000"),
            debt=Decimal("0"),
            liquidity_role="emergency_liquidity",
        ),
    ]

    return Household(
        name="Baseline household",
        current_age=BASELINE_CURRENT_AGE,
        current_date=BASELINE_CURRENT_DATE,
        planned_retirement_age=BASELINE_RETIREMENT_AGE,
        retirement_horizon_age=BASELINE_TERMINAL_AGE,
        accounts=accounts,
        liabilities=liabilities,
        income_streams=income_streams,
        expense_categories=expense_categories,
        equity_positions=[equity_position],
        liquidity_events=liquidity_events,
        real_estate=real_estate,
    )


def build_baseline_scenario() -> Scenario:
    return Scenario(name="Baseline", household=build_baseline_household())
