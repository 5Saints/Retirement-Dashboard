"""Monte Carlo stochastic simulation (PRD Section 9).

Deliberately deviates from the engine-wide Decimal-only rule (Section 11): this module
uses `numpy` `float64` arrays throughout. That is a scoped, documented exception, not a
silent one -- confirmed with the user before implementation. Monte Carlo output is
inherently a probability estimate over a distribution of uncertain future returns and
inflation, never an exact balance (Section 9: "Never present Monte Carlo probability as
a guarantee"), and the "10,000 simulations... under 15 seconds" target (Sections 9/20)
is not achievable in pure-Python Decimal arithmetic. The deterministic engine
(projection.py and everything built on it) is untouched and stays pure Decimal.

Per Section 9's own carve-out, "the company-equity price path is deterministic in the
MVP simulation; simulation risk applies to portfolio returns and inflation" -- so only
two things are randomized here: (a) the annual return credited to the taxable/401(k)
balances, and (b) the inflation rate that grows post-retirement spending year over
year. Everything else -- salary, 401(k) contribution amounts, liquidity-event proceeds,
the equity price path, mortgage payoff -- is deterministic and independent of any
simulated path, so it is computed once (not resimulated 10,000 times) from the
deterministic engine's own building blocks (equity.py, projection.irs_401k_limit).
This module also runs at annual resolution throughout, which Section 7.1 explicitly
permits ("annual resolution thereafter is acceptable for MVP") and which is what makes
the 15-second target achievable at all.

Capital-market assumptions -- the mean/stdev of returns and inflation, and their
correlation -- are not given numerically anywhere in the PRD (Section 7.3 gives only
point estimates: 6% nominal return, 3% inflation, stress cases at 4%/8%). The stdev/
correlation constants below are therefore engine-author assumptions, flagged the same
way Phase 1 flagged its tax and mortgage placeholders, pending real capital-market-
assumption input. All three non-cash accounts (taxable, 401(k), Roth) are modeled as
sharing one stochastic "portfolio return" factor rather than independent asset-class
draws, since every scenario built so far (seed.py, scenario_library.py) already gives
them the same point-estimate return -- there is no differentiated asset-class data yet
to draw correlated-but-distinct returns from. Cash always earns a deterministic 0%,
matching its `Status.CONFIRMED` baseline assumption; it never participates in market risk.

Known gap (Phase 5): this module only tracks each account's *opening balance* growing
under simulated returns plus the deterministic liquidity/401(k) inflows above -- it does
not process `household.decisions` at all (real-estate purchase/sale, spending
adjustments, Roth conversions). This has been true since Phase 3/4 integration; Phase
5's Roth conversions make it more visible, since a scenario that relies on conversions
to move wealth into the (tax-free-on-withdrawal) Roth bucket will have that movement
silently ignored by Monte Carlo, understating the simulated Roth balance and its
after-tax withdrawal advantage. Simulating the full decision set across 10,000 vectorized
paths is a real undertaking, not attempted in this pass; flagged here rather than
silently produced as though it were complete.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np

from .equity import run_share_ledger
from .models import Scenario
from .projection import irs_401k_limit
from .spending import build_schedule
from .tax import TAX_DEFERRED_DISTRIBUTION_TAX_RATE

PORTFOLIO_RETURN_STDEV = 0.12  # engine-author assumption; not specified in the PRD
INFLATION_STDEV = 0.015  # engine-author assumption; not specified in the PRD
RETURN_INFLATION_CORRELATION = -0.2  # engine-author assumption; not specified in the PRD
DEFAULT_SIMULATIONS = 10_000  # Section 9: "Minimum 10,000 simulations per scenario"
DEFAULT_SEED = 20260101  # Section 9: "Use reproducible random seeds for test runs"
DEPLETION_TOLERANCE = 0.01  # one cent, matching money.py's cents convention


@dataclass(frozen=True)
class MonteCarloResult:
    num_simulations: int
    seed: int
    success_probability: float
    median_terminal_balance: float
    percentile_10: float
    percentile_25: float
    percentile_75: float
    percentile_90: float
    minimum_portfolio_balance_median: float
    depletion_ages: list[float]


def _liquidity_proceeds_by_year(scenario: Scenario, retirement_date: date) -> dict[int, float]:
    household = scenario.household
    equity_position = household.equity_positions[0]
    steps = run_share_ledger(equity_position, household.liquidity_events, retirement_date)
    by_year: dict[int, float] = {}
    for step in steps:
        year = step.event.resolve_date(retirement_date).year
        by_year[year] = by_year.get(year, 0.0) + float(step.result.invested)
    return by_year


def run_monte_carlo(
    scenario: Scenario,
    retirement_date: date,
    terminal_age: int | None = None,
    num_simulations: int = DEFAULT_SIMULATIONS,
    seed: int = DEFAULT_SEED,
) -> MonteCarloResult:
    household = scenario.household
    horizon_age = terminal_age if terminal_age is not None else scenario.terminal_age
    current_year = household.current_date.year
    retirement_year = retirement_date.year
    terminal_year = current_year + (horizon_age - household.current_age)
    years = list(range(current_year, terminal_year + 1))
    n_years = len(years)

    liquidity_by_year = _liquidity_proceeds_by_year(scenario, retirement_date)
    distribution_tax_rate = float(TAX_DEFERRED_DISTRIBUTION_TAX_RATE.value)
    base_spending = float(
        build_schedule(
            household.expense_categories, retirement_year, scenario.retirement_inflation_rate
        ).first_year_total
    )

    portfolio_mean = float(household.accounts["taxable"].annual_return.value)
    inflation_mean = float(scenario.retirement_inflation_rate)
    covariance = np.array(
        [
            [PORTFOLIO_RETURN_STDEV**2, RETURN_INFLATION_CORRELATION * PORTFOLIO_RETURN_STDEV * INFLATION_STDEV],
            [RETURN_INFLATION_CORRELATION * PORTFOLIO_RETURN_STDEV * INFLATION_STDEV, INFLATION_STDEV**2],
        ]
    )
    rng = np.random.default_rng(seed)
    draws = rng.multivariate_normal(
        mean=[portfolio_mean, inflation_mean], cov=covariance, size=(n_years, num_simulations)
    )
    portfolio_returns = draws[:, :, 0]
    inflation_rates = draws[:, :, 1]

    cash = np.full(num_simulations, float(household.accounts["cash"].opening_balance))
    taxable = np.full(num_simulations, float(household.accounts["taxable"].opening_balance))
    k401 = np.full(num_simulations, float(household.accounts["401k"].opening_balance))
    roth_opening = float(household.accounts["roth"].opening_balance) if "roth" in household.accounts else 0.0
    roth = np.full(num_simulations, roth_opening)

    spending_target = np.full(num_simulations, base_spending)
    min_balance = np.full(num_simulations, np.inf)
    depletion_year = np.full(num_simulations, np.nan)

    for index, year in enumerate(years):
        age = household.current_age + (year - current_year)
        is_retired = year >= retirement_year
        port_return = portfolio_returns[index]

        liquidity_amount = liquidity_by_year.get(year, 0.0)
        if liquidity_amount:
            taxable = taxable + liquidity_amount

        if not is_retired:
            k401 = k401 + float(irs_401k_limit(year, age))
        else:
            if year > retirement_year:
                spending_target = spending_target * (1 + inflation_rates[index])
            remaining = spending_target.copy()

            draw_cash = np.minimum(cash, remaining)
            cash = cash - draw_cash
            remaining = remaining - draw_cash

            draw_taxable = np.minimum(taxable, np.maximum(remaining, 0.0))
            taxable = taxable - draw_taxable
            remaining = remaining - draw_taxable

            gross_needed = np.maximum(remaining, 0.0) / (1 - distribution_tax_rate)
            draw_401k = np.minimum(k401, gross_needed)
            k401 = k401 - draw_401k
            remaining = remaining - draw_401k * (1 - distribution_tax_rate)

            draw_roth = np.minimum(roth, np.maximum(remaining, 0.0))
            roth = roth - draw_roth
            remaining = remaining - draw_roth

            newly_depleted = (remaining > DEPLETION_TOLERANCE) & np.isnan(depletion_year)
            depletion_year[newly_depleted] = year

        taxable = taxable * (1 + port_return)
        k401 = k401 * (1 + port_return)
        roth = roth * (1 + port_return)

        min_balance = np.minimum(min_balance, cash + taxable + k401 + roth)

    terminal_balance = cash + taxable + k401 + roth
    success = np.isnan(depletion_year)
    depletion_ages = [
        float(household.current_age + (year - current_year)) for year in depletion_year[~success]
    ]

    return MonteCarloResult(
        num_simulations=num_simulations,
        seed=seed,
        success_probability=float(np.mean(success)),
        median_terminal_balance=float(np.median(terminal_balance)),
        percentile_10=float(np.percentile(terminal_balance, 10)),
        percentile_25=float(np.percentile(terminal_balance, 25)),
        percentile_75=float(np.percentile(terminal_balance, 75)),
        percentile_90=float(np.percentile(terminal_balance, 90)),
        minimum_portfolio_balance_median=float(np.median(min_balance)),
        depletion_ages=depletion_ages,
    )
