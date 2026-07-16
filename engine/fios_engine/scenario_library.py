"""Required built-in scenarios (Section 8.1) and named templates (Section 28).

Every builder takes a parent scenario (normally the baseline from `seed.py`) and
returns an independent clone via `scenario_engine.clone_scenario`, with each field
change recorded through `record_change` for the Section 28 audit trail.

Several scenarios need a concrete numeric assumption the PRD names only qualitatively
("Conservative returns", "High inflation", "Lower company payout", "Higher tax rate on
company payouts"). Per Section 23 ("any ambiguity must be represented as an explicit
assumption, not guessed silently"), each such choice is called out in its builder's
docstring and recorded as a `Status.ASSUMPTION` change rather than picked silently.

Not implemented here: "Immediate 25% market decline at retirement, extended to shock
the company-equity price path alongside the portfolio" (Section 8.1). `market_decline`
below only shocks the equity price path -- the mechanism this engine already has
(`PricePathAnchor`). Shocking account balances too needs a new projection-engine
concept (a balance-level shock event at an arbitrary date), which doesn't exist yet;
see docs/delivery-plan.md's Phase 3 scope note.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from .models import (
    Decision,
    DecisionType,
    InterpolationMode,
    PricePathAnchor,
    Scenario,
    Status,
    Valued,
)
from .scenario_engine import clone_scenario, record_change

CONSERVATIVE_RETURN = Decimal("0.04")  # Section 7.3 stress case
OPTIMISTIC_RETURN = Decimal("0.08")  # Section 7.3 stress case
HIGH_INFLATION_RATE = Decimal("0.05")  # not specified in the PRD; engine-author assumption
HIGHER_TAX_DELTA = Decimal("0.10")  # not specified; engine-author assumption (+10 points)
LOWER_PAYOUT_ANCHOR_PRICE = Decimal("40000")  # not specified; engine-author assumption


def _set_all_account_returns(scenario, rate: Decimal, label: str) -> None:
    for name, account in scenario.household.accounts.items():
        if account.tax_treatment == "cash":
            continue
        old = account.annual_return
        account.annual_return = Valued(rate, Status.ASSUMPTION, label)
        record_change(
            scenario, f"household.accounts[{name}].annual_return", old.value, rate, label,
            f"{scenario.name} built-in scenario (Section 8.1)",
        )


def conservative_returns(parent) -> Scenario:
    scenario = clone_scenario(parent, "Conservative returns")
    _set_all_account_returns(scenario, CONSERVATIVE_RETURN, "Section 7.3 stress case (4%)")
    return scenario


def expected_returns(parent) -> Scenario:
    """Definitionally identical to the baseline's own 6% assumption; provided as a
    named scenario for symmetry with conservative/optimistic (Section 8.1)."""
    return clone_scenario(parent, "Expected returns")


def optimistic_returns(parent) -> Scenario:
    scenario = clone_scenario(parent, "Optimistic returns")
    _set_all_account_returns(scenario, OPTIMISTIC_RETURN, "Section 7.3 stress case (8%)")
    return scenario


def high_inflation(parent, inflation_rate: Decimal = HIGH_INFLATION_RATE) -> Scenario:
    scenario = clone_scenario(parent, "High inflation")
    old = scenario.retirement_inflation_rate
    scenario.retirement_inflation_rate = inflation_rate
    record_change(
        scenario, "scenario.retirement_inflation_rate", old, inflation_rate,
        "engine-author assumption (not specified in PRD Section 8.1)",
        "High inflation built-in scenario",
    )
    return scenario


def higher_tax_on_company_payouts(parent, delta: Decimal = HIGHER_TAX_DELTA) -> Scenario:
    scenario = clone_scenario(parent, "Higher tax rate on company payouts")
    for i, event in enumerate(scenario.household.liquidity_events):
        old = event.tax_rate
        new_rate = old.value + delta
        event.tax_rate = Valued(new_rate, Status.ASSUMPTION, "Higher tax built-in scenario")
        record_change(
            scenario, f"household.liquidity_events[{i}].tax_rate", old.value, new_rate,
            "engine-author assumption (delta not specified in PRD Section 8.1)",
            "Higher tax rate on company payouts built-in scenario",
        )
    return scenario


def lower_company_payout(parent, anchor_price: Decimal = LOWER_PAYOUT_ANCHOR_PRICE) -> Scenario:
    """Reparameterizes the liquidation-date price anchor lower (CR-001/CR-004), "the
    designated stress vehicle for share-price risk" per Section 8.1."""
    scenario = clone_scenario(parent, "Lower company payout")
    equity_position = scenario.household.equity_positions[0]
    for i, anchor in enumerate(equity_position.anchors):
        if anchor.status is Status.ASSUMPTION:
            old_price = anchor.price
            equity_position.anchors[i] = PricePathAnchor(
                anchor.effective_date, anchor_price, Status.ASSUMPTION, "Lower company payout built-in scenario"
            )
            record_change(
                scenario, f"equity_position.anchors[{anchor.effective_date}]", old_price, anchor_price,
                "engine-author assumption (not specified in PRD Section 8.1)",
                "Lower company payout built-in scenario",
            )
    return scenario


def market_decline(parent) -> Scenario:
    """Partial implementation -- see module docstring. Adds a -25% price-path anchor
    at the household's own planned retirement date; does not shock account balances."""
    scenario = clone_scenario(parent, "Market decline at retirement")
    household = scenario.household
    equity_position = household.equity_positions[0]
    shock_date = household.retirement_date
    pre_shock_price = equity_position.resolve_price(shock_date)
    shocked_price = pre_shock_price * Decimal("0.75")
    equity_position.anchors.append(
        PricePathAnchor(shock_date, shocked_price, Status.ASSUMPTION, "Market decline built-in scenario")
    )
    equity_position.interpolation_mode = InterpolationMode.STEP
    record_change(
        scenario, "equity_position.anchors[+]", pre_shock_price, shocked_price,
        "Section 8.1 immediate 25% market decline (equity price path only; see module docstring)",
        "Market decline built-in scenario",
        effective_date=shock_date,
    )
    return scenario


def retire_at_age(parent, age: int) -> Scenario:
    """Covers Section 28's "retire now, retire at 57/58/59" templates and Section 8.1's
    "retire one year earlier/later" (call with `planned_retirement_age - 1` or `+ 1`).
    All retirement-timing scenarios inherit the anchored-real spending rule and
    retirement-linked liquidation with no special casing (Section 8.1), which already
    holds here since both derive from `household.retirement_date`."""
    scenario = clone_scenario(parent, f"Retire at age {age}")
    old = scenario.household.planned_retirement_age
    scenario.household.planned_retirement_age = age
    record_change(
        scenario, "household.planned_retirement_age", old, age,
        "user-specified retirement-timing template", "Retirement-timing built-in scenario",
    )
    return scenario


def reduce_discretionary_spending(parent, fraction: Decimal) -> Scenario:
    """Scales every discretionary (non-essential) expense category's anchor amount
    down by `fraction`, leaving essential categories and the essential/discretionary
    split's absolute essential dollars untouched (Section 4.9)."""
    scenario = clone_scenario(parent, f"Reduce discretionary spending {fraction:.0%}")
    for i, category in enumerate(scenario.household.expense_categories):
        if category.essential:
            continue
        old = category.anchor_amount
        category.anchor_amount = old * (1 - fraction)
        record_change(
            scenario, f"household.expense_categories[{i}].anchor_amount", old, category.anchor_amount,
            "user-specified decision", "Reduce discretionary spending built-in scenario",
        )
    return scenario


def increase_spending(
    parent, additional_annual_amount: Decimal, effective_date: date | None = None, recurring: bool = True
) -> Scenario:
    """Appends a SPENDING_ADJUSTMENT decision effective at `effective_date` (default:
    the scenario's own retirement date)."""
    scenario = clone_scenario(parent, "Increase spending")
    household = scenario.household
    effective = effective_date if effective_date is not None else household.retirement_date
    household.decisions.append(
        Decision(
            DecisionType.SPENDING_ADJUSTMENT,
            effective,
            additional_annual_amount,
            recurring_effect=recurring,
            description="Increase spending built-in scenario",
        )
    )
    record_change(
        scenario, "household.decisions[+]", None, additional_annual_amount,
        "user-specified decision", "Increase spending built-in scenario", effective_date=effective,
    )
    return scenario


def purchase_additional_real_estate(
    parent, amount: Decimal, effective_date: date, funding_source: str = "taxable", description: str = ""
) -> Scenario:
    scenario = clone_scenario(parent, "Purchase additional real estate")
    scenario.household.decisions.append(
        Decision(
            DecisionType.REAL_ESTATE_PURCHASE,
            effective_date,
            amount,
            funding_source=funding_source,
            description=description or "Additional property",
        )
    )
    record_change(
        scenario, "household.decisions[+]", None, amount,
        "user-specified decision", "Purchase additional real estate built-in scenario",
        effective_date=effective_date,
    )
    return scenario


def emergency_lake_home_sale(
    parent, effective_date: date, funding_source: str = "taxable"
) -> Scenario:
    scenario = clone_scenario(parent, "Emergency lake-home sale")
    scenario.household.decisions.append(
        Decision(
            DecisionType.REAL_ESTATE_SALE,
            effective_date,
            Decimal("0"),
            funding_source=funding_source,
            description="Lake home",
        )
    )
    record_change(
        scenario, "household.decisions[+]", None, "Lake home",
        "user-specified decision", "Emergency lake-home sale built-in scenario (Section 4.8)",
        effective_date=effective_date,
    )
    return scenario


def roth_conversion(
    parent, amount: Decimal, effective_date: date, funding_source: str = "taxable", recurring: bool = False
) -> Scenario:
    """Section 7.5: "Support Roth-conversion scenarios between retirement and required
    minimum distributions." `amount` is the gross (pre-tax) sum moved from the 401(k)
    to the Roth account each occurrence; the tax due is paid from `funding_source`, not
    from the converted amount (see `models.DecisionType.ROTH_CONVERSION`)."""
    scenario = clone_scenario(parent, "Roth conversion")
    scenario.household.decisions.append(
        Decision(
            DecisionType.ROTH_CONVERSION,
            effective_date,
            amount,
            funding_source=funding_source,
            recurring_effect=recurring,
        )
    )
    record_change(
        scenario, "household.decisions[+]", None, amount,
        "user-specified decision", "Roth conversion built-in scenario (Section 7.5)",
        effective_date=effective_date,
    )
    return scenario


def use_proportional_withdrawals(parent) -> Scenario:
    """Section 7.5: "Allow proportional withdrawals across accounts." A zero-cost
    mechanical change (no dollar amount, no funding source) rather than a financial
    decision, useful as a free candidate in the recommendation engine (Phase 6a)."""
    scenario = clone_scenario(parent, "Proportional withdrawals")
    old = scenario.withdrawal_strategy
    scenario.withdrawal_strategy = "proportional"
    record_change(
        scenario, "scenario.withdrawal_strategy", old, "proportional",
        "user-specified decision", "Proportional withdrawal built-in scenario (Section 7.5)",
    )
    return scenario
