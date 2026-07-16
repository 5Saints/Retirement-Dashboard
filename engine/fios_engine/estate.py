"""Legacy Value / estate projections (PRD Section 5, 25; Phase 7).

Section 5: "Legacy Value | Projected estate value at selected ages | Financial assets
plus net real-estate equity less debts." That definition is exactly
`projection.PeriodResult.net_worth` (assets, including real estate, less liabilities --
see `metrics.net_worth`) evaluated at a candidate age's date; no new calculation exists
here beyond naming and packaging that existing figure as "Legacy Value" and fixing the
ages the PRD asks for (75, 85, 95 -- Sections 8.2, 13).

Section 6.1/24: "Terminal estate is informational unless the user explicitly enables a
legacy floor" and "Legacy preservation is informational only and must not delay
retirement" -- this module never gates or influences WOA/SAS; it only reports.

`age_date`/`net_worth_at_age` were originally private to `comparison.py`; they moved
here (and `comparison.py` now imports them) once Phase 7 needed the same "value at a
given age" logic for a *single* scenario, not just a baseline/alternative diff.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from .models import Scenario
from .projection import ProjectionOutput, add_months, run_projection

LEGACY_REPORT_AGES = (75, 85, 95)


def age_date(scenario: Scenario, age: int) -> date:
    household = scenario.household
    return add_months(household.current_date, (age - household.current_age) * 12)


def net_worth_at_age(projection: ProjectionOutput, scenario: Scenario, age: int) -> Decimal | None:
    target = age_date(scenario, age)
    matches = [p for p in projection.periods if p.period_date >= target]
    return matches[0].net_worth if matches else None


def legacy_values(
    scenario: Scenario,
    retirement_date: date | None = None,
    terminal_age: int | None = None,
    ages: tuple[int, ...] = LEGACY_REPORT_AGES,
) -> dict[int, Decimal | None]:
    """Legacy Value at each of `ages` for this scenario on its own (not a before/after
    diff -- see `comparison.py` for that). `None` for an age past the projection's own
    horizon."""
    horizon_age = terminal_age if terminal_age is not None else scenario.terminal_age
    projection = run_projection(
        scenario,
        terminal_age=max(horizon_age, max(ages)),
        retirement_date=retirement_date,
    )
    return {age: net_worth_at_age(projection, scenario, age) for age in ages}
