"""Tests for the Retirement Readiness Score (Section 25.1), implementing
docs/rrs-normalization-spec.md.
"""

from decimal import Decimal

from fios_engine.models import PricePathAnchor, Status, Valued
from fios_engine.retirement_readiness import (
    CRI_WEIGHT,
    FM_WEIGHT,
    LCR_WEIGHT,
    RSP_WEIGHT,
    WOA_PROGRESS_WEIGHT,
    _cri_score,
    _fm_score,
    _lcr_score,
    _rsp_score,
    assumption_confidence_percent,
    compute_rrs,
)
from fios_engine.seed import build_baseline_scenario


def test_component_weights_sum_to_one():
    assert WOA_PROGRESS_WEIGHT + RSP_WEIGHT + FM_WEIGHT + LCR_WEIGHT + CRI_WEIGHT == Decimal("1.00")


def test_worked_example_matches_design_doc():
    """Golden test for docs/rrs-normalization-spec.md Section 6's worked example."""
    scenario = build_baseline_scenario()

    result = compute_rrs(scenario)

    assert abs(result.overall_score - Decimal("73.5")) < Decimal("1")
    assert result.hard_constraint_failed is False
    assert result.achievable is True
    assert Decimal("52") < result.confidence_percent < Decimal("54")


def test_hard_constraint_failure_is_forced_when_woa_is_not_achievable():
    scenario = build_baseline_scenario()
    scenario.monte_carlo_enabled = False
    scenario.terminal_age = scenario.household.current_age + 1

    result = compute_rrs(scenario)

    assert result.achievable is False
    assert result.hard_constraint_failed is True
    assert result.hard_constraint_detail is not None
    woa_component = next(c for c in result.components if c.name == "Work-Optional Age progress")
    assert woa_component.score == Decimal("0")


def test_rsp_score_at_or_above_threshold_is_100():
    scenario = build_baseline_scenario()

    score, _ = _rsp_score(scenario, 0.90)
    above_score, _ = _rsp_score(scenario, 0.95)

    assert score == Decimal("100")
    assert above_score == Decimal("100")


def test_rsp_score_scales_linearly_below_threshold():
    scenario = build_baseline_scenario()

    score, _ = _rsp_score(scenario, 0.45)

    assert score == Decimal("50")


def test_fm_score_clamps_at_the_band_edges():
    below_band, _ = _fm_score(Decimal("-100000"), Decimal("100000"))
    at_parity, _ = _fm_score(Decimal("0"), Decimal("100000"))
    above_band, _ = _fm_score(Decimal("100000"), Decimal("100000"))

    assert below_band == Decimal("0")
    assert at_parity == Decimal("50")
    assert above_band == Decimal("100")


def test_lcr_score_reaches_100_at_double_the_cash_reserve():
    scenario = build_baseline_scenario()  # cash_reserve_months == 24 -> target 4 years
    essential_annual = Decimal("100000")

    zero_liquidity, _ = _lcr_score(scenario, Decimal("0"), essential_annual)
    at_target, _ = _lcr_score(scenario, essential_annual * 4, essential_annual)
    beyond_target, _ = _lcr_score(scenario, essential_annual * 10, essential_annual)

    assert zero_liquidity == Decimal("0")
    assert at_target == Decimal("100")
    assert beyond_target == Decimal("100")


def test_cri_score_is_inverse_of_combined_concentration():
    no_concentration, _ = _cri_score(Decimal("0"), Decimal("0"), Decimal("1000000"))
    full_concentration, _ = _cri_score(Decimal("500000"), Decimal("500000"), Decimal("1000000"))
    half_concentration, _ = _cri_score(Decimal("250000"), Decimal("250000"), Decimal("1000000"))

    assert no_concentration == Decimal("100")
    assert full_concentration == Decimal("0")
    assert half_concentration == Decimal("50")


def test_confidence_percent_all_household_inputs_confirmed():
    """The two universal tax placeholders (PRE_RETIREMENT_EFFECTIVE_TAX_RATE,
    TAX_DEFERRED_DISTRIBUTION_TAX_RATE) are module-level constants, not household
    fields, so they stay Placeholder regardless of what this test confirms -- 10 of the
    12 material inputs (4 accounts incl. Roth, 2 liquidity tax rates, 2 real-estate
    appreciation rates, 2 equity anchors) become Confirmed (weight 1.00) and 2 stay
    Placeholder (weight 0.30): (10*1.00 + 2*0.30) / 12 = 88.33%, well above the
    baseline's mixed-confidence default (see test_worked_example_matches_design_doc)."""
    scenario = build_baseline_scenario()
    household = scenario.household
    for account in household.accounts.values():
        account.annual_return = Valued(account.annual_return.value, Status.CONFIRMED)
    for event in household.liquidity_events:
        event.tax_rate = Valued(event.tax_rate.value, Status.CONFIRMED)
    for real_estate in household.real_estate:
        real_estate.appreciation_rate = Valued(real_estate.appreciation_rate.value, Status.CONFIRMED)
    equity_position = household.equity_positions[0]
    equity_position.anchors = [
        PricePathAnchor(a.effective_date, a.price, Status.CONFIRMED) for a in equity_position.anchors
    ]
    household.liabilities["primary_mortgage"].payoff_boundary_date = None

    result = assumption_confidence_percent(household)

    assert abs(result - Decimal("88.33")) < Decimal("0.01")


def test_confidence_percent_all_placeholder_is_30():
    scenario = build_baseline_scenario()
    household = scenario.household
    for account in household.accounts.values():
        account.annual_return = Valued(account.annual_return.value, Status.PLACEHOLDER)
    for event in household.liquidity_events:
        event.tax_rate = Valued(event.tax_rate.value, Status.PLACEHOLDER)
    for real_estate in household.real_estate:
        real_estate.appreciation_rate = Valued(real_estate.appreciation_rate.value, Status.PLACEHOLDER)
    equity_position = household.equity_positions[0]
    equity_position.anchors = [
        PricePathAnchor(a.effective_date, a.price, Status.PLACEHOLDER) for a in equity_position.anchors
    ]
    # The two universal tax placeholders (projection.py, tax.py) are already PLACEHOLDER,
    # and the baseline mortgage's payoff plan is already a placeholder by construction.

    assert assumption_confidence_percent(household) == Decimal("30")
