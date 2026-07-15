"""Core entities (PRD Section 11), scoped to what Phase 1 (core engine) needs.

Every material input carries a `status` (PRD Section 4 / Section 27) so confirmed facts,
assumptions, placeholders, and derived values stay distinguishable through the whole pipeline —
never silently defaulted (Section 18).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional

from .money import to_cents


class Status(str, Enum):
    CONFIRMED = "confirmed"
    ASSUMPTION = "assumption"
    PLACEHOLDER = "placeholder"
    ESTIMATED = "estimated"
    DERIVED = "derived"


@dataclass(frozen=True)
class Valued:
    """A value paired with its provenance status (Section 27: source, confidence, status)."""

    value: Decimal
    status: Status
    source: str = ""


class InterpolationMode(str, Enum):
    STEP = "step"
    GEOMETRIC = "geometric"


class DateMode(str, Enum):
    FIXED = "fixed"
    RETIREMENT_LINKED = "retirement_linked"


@dataclass(frozen=True)
class PricePathAnchor:
    effective_date: date
    price: Decimal
    status: Status
    confidence: str = ""


@dataclass
class EquityPosition:
    """Share-denominated company equity (CR-001). There is deliberately no `value` field:
    dollar value is always `share_quantity * resolve_price(date)` (Appendix B). A caller
    cannot set a standalone valuation because no such attribute exists on this class."""

    description: str
    share_quantity: Decimal
    basis: Optional[Decimal]
    anchors: list[PricePathAnchor]
    interpolation_mode: InterpolationMode = InterpolationMode.STEP

    def resolve_price(self, on_date: date) -> Decimal:
        sorted_anchors = sorted(self.anchors, key=lambda a: a.effective_date)
        if not sorted_anchors:
            raise ValueError("EquityPosition has no price-path anchors")

        if self.interpolation_mode is InterpolationMode.STEP:
            applicable = [a for a in sorted_anchors if a.effective_date <= on_date]
            if applicable:
                return applicable[-1].price
            return sorted_anchors[0].price

        # Geometric: compound between the two bracketing anchors; flat before the
        # first anchor and flat after the last anchor (no extrapolation).
        before = [a for a in sorted_anchors if a.effective_date <= on_date]
        after = [a for a in sorted_anchors if a.effective_date > on_date]
        if not before:
            return sorted_anchors[0].price
        if not after:
            return before[-1].price
        lo, hi = before[-1], after[0]
        span_days = (hi.effective_date - lo.effective_date).days
        elapsed_days = (on_date - lo.effective_date).days
        if span_days == 0:
            return lo.price
        growth = (hi.price / lo.price) ** (Decimal(elapsed_days) / Decimal(span_days))
        return lo.price * growth

    def value(self, on_date: date) -> Decimal:
        return self.share_quantity * self.resolve_price(on_date)


@dataclass
class LiquidityEvent:
    equity_position: EquityPosition
    date_mode: DateMode
    shares_sold: Decimal
    tax_rate: Valued
    fixed_date: Optional[date] = None
    real_estate_allocation: Decimal = Decimal("0")
    occurred_flag: bool = False
    actual_gross: Optional[Decimal] = None
    actual_tax: Optional[Decimal] = None
    actual_net: Optional[Decimal] = None

    def resolve_date(self, retirement_date: date) -> date:
        if self.date_mode is DateMode.FIXED:
            if self.fixed_date is None:
                raise ValueError("fixed date_mode requires fixed_date")
            return self.fixed_date
        return retirement_date

    def derive(self, retirement_date: date) -> "LiquidityEventResult":
        if self.occurred_flag and self.actual_gross is not None:
            gross = self.actual_gross
            tax = self.actual_tax if self.actual_tax is not None else Decimal("0")
            net = self.actual_net if self.actual_net is not None else gross - tax
        else:
            # Gross is rounded to the cent immediately upon derivation -- it is a
            # reported value (Section 4.7 table), not an intermediate in a longer
            # chain -- and tax/net are computed from that rounded figure. This matches
            # the worked Appendix A numbers exactly (e.g. Event 1 net proceeds is
            # $1,680,000.20, which only reconciles from the cent-rounded gross).
            event_date = self.resolve_date(retirement_date)
            gross = to_cents(self.shares_sold * self.equity_position.resolve_price(event_date))
            tax = to_cents(gross * self.tax_rate.value)
            net = gross - tax
        invested = net - self.real_estate_allocation
        return LiquidityEventResult(
            gross=gross,
            tax=tax,
            net=net,
            real_estate_allocation=self.real_estate_allocation,
            invested=invested,
        )


@dataclass(frozen=True)
class LiquidityEventResult:
    gross: Decimal
    tax: Decimal
    net: Decimal
    real_estate_allocation: Decimal
    invested: Decimal


@dataclass
class Account:
    name: str
    tax_treatment: str  # "cash" | "taxable" | "tax_deferred"
    opening_balance: Decimal
    annual_return: Valued
    liquidity_class: str = "liquid"


@dataclass
class Liability:
    name: str
    opening_balance: Decimal
    rate: Optional[Valued] = None
    payment: Optional[Valued] = None
    maturity: Optional[date] = None
    payoff_boundary_date: Optional[date] = None  # placeholder rule (CR-002)


@dataclass
class IncomeStream:
    name: str
    annual_amount: Decimal
    growth_rate: Decimal
    start_date: date
    end_date: Optional[date] = None


@dataclass
class ExpenseCategory:
    name: str
    essential: bool
    anchor_amount: Decimal
    anchor_year: int = 2032


@dataclass
class RealEstate:
    name: str
    value: Decimal
    debt: Decimal
    liquidity_role: str  # "residence" | "emergency_liquidity"
    appreciation_rate: Valued = field(
        default_factory=lambda: Valued(Decimal("0.025"), Status.PLACEHOLDER, "CL-5")
    )


@dataclass
class Household:
    name: str
    current_age: int
    current_date: date
    planned_retirement_age: int
    retirement_horizon_age: int
    accounts: dict[str, Account]
    liabilities: dict[str, Liability]
    income_streams: list[IncomeStream]
    expense_categories: list[ExpenseCategory]
    equity_positions: list[EquityPosition]
    liquidity_events: list[LiquidityEvent]
    real_estate: list[RealEstate]

    @property
    def retirement_date(self) -> date:
        years_to_retirement = self.planned_retirement_age - self.current_age
        return date(
            self.current_date.year + years_to_retirement,
            self.current_date.month,
            self.current_date.day,
        )


@dataclass
class Scenario:
    """Phase 1 has exactly one scenario: the baseline. Cloning/overrides are Phase 3.

    The fields below are the Section 6.2 WOA default thresholds. `stress_return_haircut`
    is the Phase 2 deterministic stand-in for the Section 8.1 "Conservative returns"
    built-in scenario: Section 7.3 gives 6% nominal as the default post-retirement
    balanced return with "stress cases at 4% and 8%", so 0.02 reproduces the 4% stress
    case as a flat haircut off every invested account's return. The full scenario-clone
    machinery (Section 8) and Monte Carlo Success Threshold gate (Section 9) are Phases
    3 and 4; see docs/delivery-plan.md.
    """

    name: str
    household: Household
    retirement_inflation_rate: Decimal = Decimal("0.03")
    accumulation_return_rate: Decimal = Decimal("0.06")
    success_threshold: Decimal = Decimal("0.90")
    terminal_age: int = 95
    legacy_floor: Decimal = Decimal("0")
    cash_reserve_months: int = 24
    max_initial_withdrawal_warning: Decimal = Decimal("0.04")
    legacy_test_enabled: bool = False
    stress_return_haircut: Decimal = Decimal("0.02")
