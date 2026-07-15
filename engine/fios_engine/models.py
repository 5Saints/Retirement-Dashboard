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


class DecisionType(str, Enum):
    """PRD Section 11 `Decision` entity, Section 28 named-template building blocks.

    Each type is handled by a distinct code path in projection.py's monthly loop,
    analogous to how liquidity events already inject at an arbitrary month:

    - REAL_ESTATE_PURCHASE reduces the account named in `funding_source` and credits
      the zero-appreciation "additional property" bucket that Event 1's $500,000
      real-estate allocation already uses (Section 4.8's "Planned additional property"
      row); `description` is an optional human label only, since that bucket doesn't
      track distinct named properties.
    - REAL_ESTATE_SALE liquidates the `household.real_estate` entry named in
      `description` and credits the account named in `funding_source`, e.g. Section
      4.8's "permit emergency-sale scenario" for the lake home. `amount` of `0`
      (the default) sells at the property's live projected value; a positive `amount`
      overrides it (e.g. a specific negotiated price). Property debt is not netted out
      here, matching the existing convention that only `Liability` entries (the
      mortgage) carry debt into the projection -- see projection.py's real-estate note.
    - SPENDING_ADJUSTMENT changes the post-retirement monthly spending target by
      `amount` per year; pre-retirement spending is a residual (Section 4.10) and is
      not affected by this decision type.
    - ROTH_CONVERSION (Section 7.5: "Support Roth-conversion scenarios between
      retirement and required minimum distributions") moves `amount` (gross, pre-tax)
      from the 401(k) to the Roth account; the resulting ordinary-income tax (at
      `tax.TAX_DEFERRED_DISTRIBUTION_TAX_RATE`, the same placeholder rate already used
      for 401(k) distributions) is paid from `funding_source`, not from the converted
      amount itself, so the full gross amount grows tax-free in the Roth account
      afterward -- standard conversion practice, not an engine invention. A conversion
      executed at or after `Scenario.rmd_age` is flagged with a warning (not blocked),
      since Section 7.5 scopes conversions to the retirement-to-RMD window but the PRD
      doesn't specify enforcement rather than disclosure.
    """

    REAL_ESTATE_PURCHASE = "real_estate_purchase"
    REAL_ESTATE_SALE = "real_estate_sale"
    SPENDING_ADJUSTMENT = "spending_adjustment"
    ROTH_CONVERSION = "roth_conversion"


@dataclass
class Decision:
    decision_type: DecisionType
    effective_date: date
    amount: Decimal
    funding_source: str = ""
    recurring_effect: bool = True
    description: str = ""


@dataclass(frozen=True)
class AssumptionChange:
    """Section 28: "every assumption change requires an effective date, old value, new
    value, source, reason, user, and timestamp." `user`/`timestamp` are populated by
    the persistence layer this engine doesn't own yet (no DB/API exists -- see
    delivery-plan.md); this record carries everything the engine itself can attest to.
    """

    field_path: str
    old_value: object
    new_value: object
    source: str
    reason: str
    effective_date: Optional[date] = None


class RecommendationStatus(str, Enum):
    """Section 26.1's required status set, verbatim."""

    ACTIVE = "active"
    ACCEPTED = "accepted"
    COMPLETED = "completed"
    DISMISSED = "dismissed"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"


@dataclass(frozen=True)
class RecommendationRecord:
    """PRD Section 11 `Recommendation` entity / Section 26.1: "Store recommendation
    date, model version, scenario version, recommendation text, status, user response,
    expected impact, and realized impact where measurable" and "Retain the original
    recommendation and assumptions even after the baseline changes."

    This dataclass is the immutable, retained original -- every field is captured once
    at creation time (`recommendation_history.save_recommendation_set`) and never
    mutated in place. Status changes, user responses, and realized impact are appended
    as separate `RecommendationHistoryEntry` rows (Section 11's `RecommendationHistory`
    entity) rather than overwriting this record, so "the original recommendation and
    assumptions" stay retrievable exactly as generated even after the status changes or
    the baseline scenario is later edited.
    """

    id: str
    scenario_name: str
    created_at: date
    model_version: str
    scenario_version: str
    action: str
    reason: str
    decision_type: Optional[DecisionType]
    timing: date
    amount: Decimal
    funding_source: str
    confidence_level: str
    confidence_score: Decimal
    invalidation_conditions: list[str]
    assumptions_snapshot: list[str]
    expected_impact: dict[str, object]
    status: RecommendationStatus = RecommendationStatus.ACTIVE


@dataclass(frozen=True)
class RecommendationHistoryEntry:
    """PRD Section 11 `RecommendationHistory` entity."""

    recommendation_id: str
    timestamp: date
    old_status: Optional[RecommendationStatus]
    new_status: RecommendationStatus
    user_response: Optional[str] = None
    realized_impact: Optional[dict[str, object]] = None


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
    decisions: list[Decision] = field(default_factory=list)

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
    """A scenario is "a complete, immutable set of assumptions derived from a parent
    scenario" (Section 8). `parent_name`/`changes` record that lineage: `changes` is
    the Section 28 audit trail ("every assumption change requires an effective date,
    old value, new value, source, reason") for whatever `scenario_engine.clone_scenario`
    and the `scenario_library` builders did to produce this scenario from its parent.
    The baseline scenario has `parent_name=None` and an empty `changes` list.

    The threshold fields below are the Section 6.2 WOA defaults. `success_threshold`
    (Section 6.2's "sole probability parameter") gates the Monte Carlo verification step
    of the WOA solver (Section 6.3). `monte_carlo_enabled` toggles Section 6.3 steps 3-4
    off for callers that want a fast deterministic-only solve (e.g. most tests); Monte
    Carlo itself is Phase 4.

    `stress_return_haircut` drives `retirement_tests.stress_test`, the deterministic
    half of Section 6.1's stress test: it is applied *relative to this scenario's own*
    account returns (a flat haircut, deliberately not `scenario_library.conservative_returns`'
    absolute 4% floor). An absolute floor would make every scenario at or above 4%
    collapse to the identical solved WOA regardless of its own return assumption --
    discovered while wiring up Phase 4, see the Phase 4 scope note in
    docs/delivery-plan.md -- which would make the Phase 3 return-variant scenarios
    (conservative/expected/optimistic) meaningless for WOA comparison. The relative
    haircut keeps a scenario's own return assumption load-bearing while still requiring
    some margin below it. 0.02 reproduces Section 7.3's 4% stress case off the 6%
    baseline; `scenario_library.conservative_returns` remains available separately for
    an explicit "what if returns come in at exactly 4%" comparison.

    The withdrawal/guardrail fields below are Section 7.5. `withdrawal_order` defaults
    to Section 7.5's own listed order (cash, taxable, tax-deferred, Roth) -- "real
    estate" is deliberately excluded from the default order and gated behind
    `allow_real_estate_liquidation_as_last_resort=False` instead, per Section 7.5's own
    closing line: "Support emergency sale of lake home as an explicit scenario, not an
    automatic baseline action." `spending_guardrail` selects one of Section 7.5's three
    named guardrails; `discretionary_cut_fraction` is the fraction of discretionary
    spending removed under `"discretionary_cuts"` (not specified numerically in the
    PRD -- an engine-author default). `rmd_age` is the current-law Required Minimum
    Distribution age (73, per SECURE 2.0 for the baseline household's birth-year
    cohort); the PRD does not restate it, so it is flagged as an assumption here rather
    than hard-coded silently in `retirement_readiness.py` or `projection.py`.
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
    monte_carlo_enabled: bool = True
    stress_return_haircut: Decimal = Decimal("0.02")
    withdrawal_order: tuple[str, ...] = ("cash", "taxable", "401k", "roth")
    withdrawal_strategy: str = "sequential"  # "sequential" | "proportional"
    spending_guardrail: str = "full_budget"  # "full_budget" | "discretionary_cuts" | "essential_only"
    discretionary_cut_fraction: Decimal = Decimal("0.5")
    allow_real_estate_liquidation_as_last_resort: bool = False
    real_estate_last_resort_property: str = "Lake home"
    rmd_age: int = 73
    parent_name: Optional[str] = None
    changes: list[AssumptionChange] = field(default_factory=list)
