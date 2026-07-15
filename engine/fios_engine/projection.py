"""Monthly projection engine (PRD Section 7.1/7.2).

Runs the full period-processing order every month from the household's current date
through the terminal age:

    1. Open with prior period's closing balances.
    2. Apply income (salary, bonus -- Social Security/pension excluded from baseline).
    3. Calculate payroll/income-tax estimates.
    4. Apply spending and debt payments (pre-retirement spending is the consumption
       residual, Section 4.10).
    5. Apply contributions and liquidity-event allocations.
    6. Apply investment returns and asset-specific tax drag.
    7. Apply real-estate appreciation, income, expenses, and debt amortization.
    8. Calculate closing balances, net worth, investable assets, and metrics.

Two things in this module are engine-author assumptions beyond what the PRD specifies
literally, both flagged as PLACEHOLDER per Section 23 ("any ambiguity must be represented
as an explicit assumption, not guessed silently") rather than silently invented:

- `PRE_RETIREMENT_EFFECTIVE_TAX_RATE`: the PRD gives effective tax placeholders for
  liquidity events (30%) and tax-deferred distributions (25%) but not for ordinary
  salary/bonus income during accumulation, which the consumption-residual formula
  (Section 4.10) requires. The exact rate does not affect the Section 19 acceptance
  numbers because implied spending is a residual by construction -- whatever this rate
  is, `income == taxes + contributions + debt_service + implied_spending` still holds.
- `IRS_401K_LIMITS`: Section 4.5 requires "IRS maximum for applicable year" including the
  age-50 and age 60-63 catch-ups (CL-3) stored in a configurable table. Real statutory
  limits are only published a year or two ahead; out-year figures here are a placeholder
  indexing assumption, not confirmed IRS data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from .equity import concentration_risk_index, run_share_ledger
from .metrics import investable_assets, net_worth, total_assets
from .models import Scenario, Status, Valued
from .mortgage import placeholder_payoff_plan
from .spending import SpendingSchedule, build_schedule
from .tax import TAX_DEFERRED_DISTRIBUTION_TAX_RATE

PRE_RETIREMENT_EFFECTIVE_TAX_RATE = Valued(
    Decimal("0.32"),
    Status.PLACEHOLDER,
    "not specified in PRD baseline; blended federal+state+payroll estimate pending CPA confirmation",
)

# Section 4.5 / CL-3: base elective-deferral limit, age-50 catch-up, and age 60-63
# enhanced catch-up, by year. Placeholder indexing beyond the last confirmed year.
IRS_401K_LIMITS: dict[int, dict[str, Decimal]] = {
    year: {
        "base": Decimal("24000") + Decimal("500") * (year - 2026),
        "catchup_50": Decimal("8000"),
        "catchup_60_63": Decimal("12000"),
    }
    for year in range(2026, 2101)
}


def irs_401k_limit(year: int, age: int) -> Decimal:
    table = IRS_401K_LIMITS[year]
    limit = table["base"]
    if 60 <= age <= 63:
        limit += table["catchup_60_63"]
    elif age >= 50:
        limit += table["catchup_50"]
    return limit


def add_months(base: date, months: int) -> date:
    total_month_index = (base.month - 1) + months
    year = base.year + total_month_index // 12
    month = total_month_index % 12 + 1
    return date(year, month, base.day)


def annual_amount_in_year(stream, base_year: int, year: int) -> Decimal:
    """Section 4.2: `salary(year) = base * (1 + growth) ** (year - base_year)`, compounded
    once per calendar year (not monthly), same formula for any flat-growth income stream."""
    return stream.annual_amount * (1 + stream.growth_rate) ** (year - base_year)


@dataclass
class LiquidityEventOccurrence:
    event_name: str
    gross: Decimal
    tax: Decimal
    net: Decimal
    real_estate_allocation: Decimal
    invested: Decimal


@dataclass
class PeriodResult:
    period_date: date
    is_retired: bool
    gross_income: Decimal
    estimated_taxes: Decimal
    contributions_401k: Decimal
    debt_service: Decimal
    implied_pre_retirement_spending: Decimal | None
    actual_spending: Decimal | None
    liquidity_events: list[LiquidityEventOccurrence]
    account_balances: dict[str, Decimal]
    mortgage_balance: Decimal
    shares_outstanding: Decimal
    equity_value: Decimal
    real_estate_value: Decimal
    net_worth: Decimal
    investable_assets: Decimal
    concentration_vs_net_worth: Decimal
    concentration_vs_investable: Decimal
    warnings: list[str] = field(default_factory=list)


@dataclass
class ProjectionOutput:
    scenario_name: str
    periods: list[PeriodResult]

    def period_at(self, on_date: date) -> PeriodResult:
        for period in self.periods:
            if period.period_date == on_date:
                return period
        raise KeyError(f"no period at {on_date}")

    def last_period_in_year(self, year: int) -> PeriodResult:
        matches = [p for p in self.periods if p.period_date.year == year]
        if not matches:
            raise KeyError(f"no periods in year {year}")
        return matches[-1]


def run_projection(
    scenario: Scenario,
    terminal_age: int | None = None,
    retirement_date: date | None = None,
    spending_schedule: SpendingSchedule | None = None,
    return_haircut: Decimal = Decimal("0"),
) -> ProjectionOutput:
    """`retirement_date`, `spending_schedule`, and `return_haircut` let the Phase 2
    solvers (woa_solver.py, sas_solver.py) evaluate a candidate retirement date or
    candidate spending level without mutating the household's own planned retirement
    date or the Section 4.9 anchored spending schedule. `return_haircut` is the Section
    6.1 deterministic stress-test proxy (see models.Scenario.stress_return_haircut);
    it is subtracted, floored at zero, from every non-cash account's return for the
    whole horizon, since the engine does not yet model separate pre/post-retirement
    return regimes (Section 7.3 -- that split is deferred, see delivery-plan.md)."""
    household = scenario.household
    retirement_date = retirement_date if retirement_date is not None else household.retirement_date
    horizon_age = terminal_age if terminal_age is not None else household.retirement_horizon_age
    terminal_date = add_months(household.current_date, (horizon_age - household.current_age) * 12)

    equity_position = household.equity_positions[0]
    ledger_steps = run_share_ledger(equity_position, household.liquidity_events, retirement_date)
    event_by_month: dict[date, list] = {}
    for step in ledger_steps:
        resolved = step.event.resolve_date(retirement_date)
        event_by_month.setdefault(date(resolved.year, resolved.month, 1), []).append(step)

    mortgage = household.liabilities["primary_mortgage"]
    mortgage_payoff = None
    if mortgage.opening_balance > 0 and mortgage.payoff_boundary_date is not None:
        mortgage_payoff = placeholder_payoff_plan(
            mortgage.opening_balance, household.current_date, mortgage.payoff_boundary_date
        )

    monthly_rates = {
        name: max(acc.annual_return.value - (return_haircut if acc.tax_treatment != "cash" else Decimal("0")), Decimal("0")) / 12
        for name, acc in household.accounts.items()
    }
    balances = {name: acc.opening_balance for name, acc in household.accounts.items()}
    mortgage_balance = mortgage.opening_balance
    shares_outstanding = equity_position.share_quantity
    additional_property_value = Decimal("0")

    # Real-estate values track per property so each can appreciate at its own rate.
    # Debt is NOT summed from RealEstate.debt here -- Appendix A lists the $700k primary
    # residence as a gross asset value and the $100,000 mortgage as a separate liability
    # line; `mortgage_balance` (below) is the single source of truth for that debt so it
    # is never double-counted.
    re_values = {r.name: r.value for r in household.real_estate}
    re_monthly_rates = {r.name: r.appreciation_rate.value / 12 for r in household.real_estate}
    other_liability_balance = sum(
        (l.opening_balance for name, l in household.liabilities.items() if name != "primary_mortgage"),
        Decimal("0"),
    )

    salary_stream = next(s for s in household.income_streams if s.name == "Salary")
    bonus_stream = next(s for s in household.income_streams if s.name == "Annual bonus")

    if spending_schedule is None:
        spending_schedule = build_schedule(retirement_date.year, scenario.retirement_inflation_rate)

    periods: list[PeriodResult] = []
    month_index = 0
    current = household.current_date
    while current <= terminal_date:
        is_retired = current >= retirement_date
        age = household.current_age + (current.year - household.current_date.year)
        warnings: list[str] = []

        # 2. Income (salary/bonus only; Social Security excluded from baseline, Section 4.1)
        if not is_retired:
            base_year = household.current_date.year
            salary_month = annual_amount_in_year(salary_stream, base_year, current.year) / 12
            bonus_month = annual_amount_in_year(bonus_stream, base_year, current.year) / 12
            gross_income = salary_month + bonus_month
        else:
            gross_income = Decimal("0")

        # 3. Payroll/income-tax estimate
        estimated_taxes = (
            gross_income * PRE_RETIREMENT_EFFECTIVE_TAX_RATE.value if not is_retired else Decimal("0")
        )

        # 4. Spending and debt payments
        debt_service = Decimal("0")
        if not is_retired and mortgage_payoff is not None and mortgage_balance > 0:
            debt_service = min(mortgage_payoff.monthly_payment, mortgage_balance)
            mortgage_balance -= debt_service

        actual_spending = None
        implied_spending = None

        # 5. Contributions and liquidity-event allocations
        contributions_401k = Decimal("0")
        if not is_retired:
            annual_limit = irs_401k_limit(current.year, age)
            contributions_401k = annual_limit / 12
            balances["401k"] += contributions_401k

        occurrences: list[LiquidityEventOccurrence] = []
        month_key = date(current.year, current.month, 1)
        for step in event_by_month.get(month_key, []):
            shares_outstanding -= step.event.shares_sold
            result = step.result
            balances["taxable"] += result.invested
            additional_property_value += result.real_estate_allocation
            occurrences.append(
                LiquidityEventOccurrence(
                    event_name=step.event.equity_position.description,
                    gross=result.gross,
                    tax=result.tax,
                    net=result.net,
                    real_estate_allocation=result.real_estate_allocation,
                    invested=result.invested,
                )
            )

        # Consumption residual (Section 4.10): applies to salary/bonus only, never to
        # liquidity-event proceeds, which follow their allocation rules exclusively.
        if not is_retired:
            implied_spending = gross_income - estimated_taxes - contributions_401k - debt_service
        else:
            monthly_target = spending_schedule.spending_in_year(current.year) / 12
            actual_spending = _withdraw_for_spending(balances, monthly_target, warnings)

        # 6. Investment returns and tax drag (tax drag on taxable/401k defaults to zero
        # per Section 4.6/22 pending user configuration)
        for name in balances:
            balances[name] *= 1 + monthly_rates[name]

        # 7. Real estate appreciation (additional property has zero appreciation by
        # default per Section 4.8, until specified; primary/lake home use the 2.5%
        # placeholder rate from Section 22/CL-5)
        for name in re_values:
            re_values[name] *= 1 + re_monthly_rates[name]
        real_estate_value = sum(re_values.values(), Decimal("0")) + additional_property_value

        equity_value = shares_outstanding * equity_position.resolve_price(current)
        assets = total_assets(balances, equity_value, real_estate_value)
        liabilities = mortgage_balance + other_liability_balance
        nw = net_worth(assets, liabilities)
        inv_assets = investable_assets(balances, equity_value)

        periods.append(
            PeriodResult(
                period_date=current,
                is_retired=is_retired,
                gross_income=gross_income,
                estimated_taxes=estimated_taxes,
                contributions_401k=contributions_401k,
                debt_service=debt_service,
                implied_pre_retirement_spending=implied_spending,
                actual_spending=actual_spending,
                liquidity_events=occurrences,
                account_balances=dict(balances),
                mortgage_balance=mortgage_balance,
                shares_outstanding=shares_outstanding,
                equity_value=equity_value,
                real_estate_value=real_estate_value,
                net_worth=nw,
                investable_assets=inv_assets,
                concentration_vs_net_worth=concentration_risk_index(equity_value, nw),
                concentration_vs_investable=concentration_risk_index(equity_value, inv_assets),
                warnings=warnings,
            )
        )

        month_index += 1
        current = add_months(household.current_date, month_index)

    return ProjectionOutput(scenario_name=scenario.name, periods=periods)


def _withdraw_for_spending(
    balances: dict[str, Decimal], monthly_target: Decimal, warnings: list[str]
) -> Decimal:
    """Sequential withdrawal order: cash, taxable, tax-deferred (Section 7.5 default
    order; Roth/real-estate sale not modeled in Phase 1 baseline). Tax-deferred
    withdrawals are grossed up by the distribution tax placeholder so the household
    still nets the target spending amount after tax."""
    remaining = monthly_target
    for account_name in ("cash", "taxable"):
        available = balances[account_name]
        draw = min(available, remaining)
        balances[account_name] -= draw
        remaining -= draw
        if remaining <= 0:
            return monthly_target

    if remaining > 0:
        gross_needed = remaining / (1 - TAX_DEFERRED_DISTRIBUTION_TAX_RATE.value)
        available = balances["401k"]
        draw = min(available, gross_needed)
        balances["401k"] -= draw
        net_from_401k = draw * (1 - TAX_DEFERRED_DISTRIBUTION_TAX_RATE.value)
        remaining -= net_from_401k
        if remaining > 0:
            warnings.append(
                f"portfolio depleted; unable to fund {remaining} of monthly spending target"
            )
    return monthly_target - max(remaining, Decimal("0"))
