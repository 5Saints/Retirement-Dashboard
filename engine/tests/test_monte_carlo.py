"""Tests for the Monte Carlo engine (PRD Section 9), including the Section 20 boundary
tests it explicitly calls out: "zero returns, negative returns, high inflation,
depletion, and terminal-age handling," plus a "Monte Carlo distribution sanity check"
and the Section 9/20 performance target.
"""

import time
from datetime import date
from decimal import Decimal

from fios_engine.models import Status, Valued
from fios_engine.monte_carlo import run_monte_carlo
from fios_engine.seed import build_baseline_scenario

CANDIDATE = date(2048, 4, 1)


def test_reproducible_seed_gives_identical_results():
    """Section 9: "Use reproducible random seeds for test runs.\""""
    scenario = build_baseline_scenario()

    first = run_monte_carlo(scenario, CANDIDATE, num_simulations=500, seed=42)
    second = run_monte_carlo(scenario, CANDIDATE, num_simulations=500, seed=42)

    assert first == second


def test_different_seeds_give_different_results():
    scenario = build_baseline_scenario()

    first = run_monte_carlo(scenario, CANDIDATE, num_simulations=500, seed=1)
    second = run_monte_carlo(scenario, CANDIDATE, num_simulations=500, seed=2)

    assert first.success_probability != second.success_probability


def test_success_probability_and_percentiles_are_sane():
    """Monte Carlo distribution sanity check (Section 20)."""
    scenario = build_baseline_scenario()

    result = run_monte_carlo(scenario, CANDIDATE, num_simulations=2000)

    assert 0.0 <= result.success_probability <= 1.0
    assert result.percentile_10 <= result.percentile_25
    assert result.percentile_25 <= result.median_terminal_balance
    assert result.median_terminal_balance <= result.percentile_75
    assert result.percentile_75 <= result.percentile_90
    assert result.minimum_portfolio_balance_median >= 0.0


def test_performance_10k_simulations_well_under_target():
    """Section 9/20: "10,000-run Monte Carlo under 15 seconds"."""
    scenario = build_baseline_scenario()

    start = time.time()
    run_monte_carlo(scenario, CANDIDATE, num_simulations=10_000)
    elapsed = time.time() - start

    assert elapsed < 15.0


def test_boundary_zero_returns_does_not_crash_and_lowers_success():
    scenario = build_baseline_scenario()
    baseline_result = run_monte_carlo(scenario, CANDIDATE, num_simulations=2000, seed=7)

    for name, account in scenario.household.accounts.items():
        if account.tax_treatment != "cash":
            account.annual_return = Valued(Decimal("0"), Status.ASSUMPTION, "zero-return boundary test")

    zero_return_result = run_monte_carlo(scenario, CANDIDATE, num_simulations=2000, seed=7)

    assert zero_return_result.success_probability <= baseline_result.success_probability


def test_boundary_negative_returns_does_not_crash():
    scenario = build_baseline_scenario()
    for name, account in scenario.household.accounts.items():
        if account.tax_treatment != "cash":
            account.annual_return = Valued(Decimal("-0.02"), Status.ASSUMPTION, "negative-return boundary test")

    result = run_monte_carlo(scenario, CANDIDATE, num_simulations=2000, seed=7)

    assert 0.0 <= result.success_probability <= 1.0
    assert result.success_probability < 0.5


def test_boundary_high_inflation_lowers_success_probability():
    scenario = build_baseline_scenario()
    baseline_result = run_monte_carlo(scenario, CANDIDATE, num_simulations=2000, seed=7)

    scenario.retirement_inflation_rate = Decimal("0.10")
    high_inflation_result = run_monte_carlo(scenario, CANDIDATE, num_simulations=2000, seed=7)

    assert high_inflation_result.success_probability <= baseline_result.success_probability


def test_boundary_depletion_is_detected_with_insufficient_assets():
    """Forcing near-certain depletion: inflate the anchored spending target far beyond
    what any plausible portfolio (including the deterministic liquidity-event
    proceeds) could sustain, rather than draining opening balances -- the fixed-date
    liquidity events would otherwise still deliver millions in proceeds regardless of
    the starting balances."""
    scenario = build_baseline_scenario()
    for category in scenario.household.expense_categories:
        category.anchor_amount = category.anchor_amount * 50

    result = run_monte_carlo(scenario, CANDIDATE, num_simulations=1000, seed=7)

    assert result.success_probability < 0.05
    assert len(result.depletion_ages) > 900
    for age in result.depletion_ages:
        assert scenario.household.current_age <= age <= scenario.terminal_age


def test_terminal_age_handling_shortens_the_horizon():
    scenario = build_baseline_scenario()

    short_horizon = run_monte_carlo(scenario, CANDIDATE, terminal_age=90, num_simulations=1000, seed=7)
    long_horizon = run_monte_carlo(scenario, CANDIDATE, terminal_age=95, num_simulations=1000, seed=7)

    # A shorter horizon gives the portfolio less time to deplete, so success
    # probability at the same candidate date should never be lower.
    assert short_horizon.success_probability >= long_horizon.success_probability
