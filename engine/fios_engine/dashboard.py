"""Engine-output bundle for WOA, FID, SAS, and Freedom Margin -- the Phase 2 slice of
the "minimum engine output" (Section 21/Section 5 table). There is no dashboard API or
frontend yet (those are later phases per docs/delivery-plan.md); this is the
calculation-layer result object those layers will eventually serve.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .models import Scenario
from .sas_solver import SASResult, solve_sas
from .spending import first_year_spending
from .woa_solver import WOAResult, solve_woa


@dataclass(frozen=True)
class DashboardSummary:
    woa: WOAResult
    fid: date | None
    sas: SASResult | None
    freedom_margin: Decimal | None


def compute_dashboard_summary(scenario: Scenario) -> DashboardSummary:
    woa = solve_woa(scenario)
    if not woa.achievable or woa.candidate_date is None:
        return DashboardSummary(woa=woa, fid=None, sas=None, freedom_margin=None)

    fid = woa.candidate_date
    sas = solve_sas(scenario, fid)
    desired_spending = first_year_spending(fid.year, scenario.retirement_inflation_rate)
    freedom_margin = sas.sustainable_spending - desired_spending
    return DashboardSummary(woa=woa, fid=fid, sas=sas, freedom_margin=freedom_margin)
