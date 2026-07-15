# RRS Normalization Specification

Pre-implementation design document required by Section 23 ("Deliver the RRS normalization
specification as a design document before phase 4b begins") and CR-006 ("RRS normalization
specification added as a pre-4b design deliverable"). Reviewed as part of Phase 4b's
implementation commit, per this project's established practice of shipping pre-implementation
deliverables alongside the phase they gate (see docs/architecture.md, docs/erd.md,
docs/calculation-spec.md, docs/threat-model.md from Phase 1).

## 1. Scope

The Retirement Readiness Score (RRS) is a configurable 0-100 composite (Section 25.1) built
from five weighted components, all already computable from the Phase 1-4 engine:

| Component | Weight | Source |
|---|---|---|
| Work-Optional Age progress | 35% | `woa_solver.solve_woa` |
| Retirement Success Probability (RSP) | 30% | `monte_carlo.run_monte_carlo` (via `dashboard.compute_dashboard_summary`) |
| Freedom Margin (FM) | 20% | `dashboard.compute_dashboard_summary` |
| Liquidity Coverage (LCR) | 10% | account balances + `retirement_tests.essential_fraction` |
| Concentration Risk (CRI) | 5% | equity + real estate value vs. net worth |

Weights and every normalization constant below are exposed as `Scenario` fields or named
constants (Section 25.1: "the initial default weighting is configurable and must be
transparent"), never hard-coded inline in the scoring formula.

None of the five component *definitions* are new engine-author inventions -- WOA, RSP, FM,
liquidity, and concentration are all Sections 5/6/9/25 concepts the engine already computes.
What Section 23 asks this document to specify is the **normalization**: the mapping from each
component's natural units (a date, a probability, a dollar amount, a year count, a ratio) onto
a common 0-100 scale, since the PRD does not give that mapping numerically anywhere (Section
25.1 says only that RSP's normalization logic is "defined in the phase-4b design document" --
i.e., here).

## 2. Component normalization

### 2.1 Work-Optional Age progress (35%)

Defined relative to the solver's own search window (`woa_solver._last_search_date`), so it
uses no new arbitrary constant: 0 at the latest possible achievable date, 100 at "achievable
today."

```
progress = (last_search_date - woa_date) / (last_search_date - current_date)
woa_progress_score = 100 * clamp(progress, 0, 1)
```

If WOA is Not Achievable, `woa_progress_score = 0` (a hard floor, not merely a low score --
see Section 4).

Rationale: this ties "progress" to the same boundary the solver already treats as the edge of
feasibility (`terminal_age` minus `cash_reserve_months`), rather than an arbitrary "0-40 years"
scale. A household whose WOA sits right at that boundary has made the least possible progress
relative to what this model can even certify; one whose WOA is today has made all of it.

### 2.2 Retirement Success Probability (30%)

Section 25.1 states the boundary condition directly: 100 at or above the Success Threshold,
scaling down below it. The PRD does not specify the curve below threshold; a linear scale
from 0% probability is the simplest monotonic choice consistent with the stated boundary and
requires no additional constant beyond the Success Threshold that already exists
(`Scenario.success_threshold`):

```
rsp_score = 100                                        if success_probability >= success_threshold
rsp_score = 100 * (success_probability / success_threshold)   otherwise
```

### 2.3 Freedom Margin (20%)

FM is an unbounded dollar amount (SAS minus desired spending); it is normalized as a
percentage of desired spending, then clamped to a symmetric band:

```
fm_ratio = freedom_margin / desired_spending
fm_score = 100 * clamp((fm_ratio + 0.5) / 1.0, 0, 1)
```

i.e. a 50%+ shortfall scores 0, parity (FM = 0) scores 50, and a 50%+ surplus scores 100.
The +/-50% band is an engine-author assumption (not specified in the PRD): it treats a plan
that could sustain 1.5x its desired spending as already at the ceiling of "excellent," since
distinguishing a 150% surplus from a 500% surplus adds little decision-relevant information at
a 0-100 display resolution.

### 2.4 Liquidity Coverage (10%)

LCR is liquid assets (Section 25's `LIQUID_CLASSES` -- cash and taxable, matching
`retirement_tests.liquidity_test`) divided by essential annual spending, in years. Normalized
against **twice** the Section 6.2 cash-reserve requirement (`Scenario.cash_reserve_months`),
reusing the existing configured minimum rather than a new constant:

```
target_years = 2 * (cash_reserve_months / 12)
lcr_score = 100 * clamp(lcr_years / target_years, 0, 1)
```

Rationale: the cash-reserve requirement is already the plan's own definition of "the minimum
liquidity a passing plan must hold" (Section 6.1's liquidity test uses exactly this
threshold). Scoring 100 at *double* that minimum treats the regulatory/test floor as merely
adequate (50 on this component) and rewards a comfortable buffer above it, without inventing an
unrelated absolute year count.

### 2.5 Concentration Risk (5%)

Section 25 defines CRI as exposure to "employer equity, individual securities, and illiquid
real estate." This engine does not model individual-security positions distinct from the
employer-equity ledger (there is only one `EquityPosition`, Appendix A/Section 4.7), so that
term is out of scope here and flagged, not silently assumed zero-risk. CRI is computed as
combined equity-plus-real-estate exposure over net worth, at the same evaluation date as the
other components:

```
cri = (equity_value + real_estate_value) / net_worth
cri_score = 100 * clamp(1 - cri, 0, 1)
```

This is deliberately a *different, broader* ratio than `equity.concentration_risk_index`
(which is equity-only, feeding the Section 6.1 concentration *test*, not the RRS component) --
the two serve different purposes and must not be conflated. `retirement_readiness.py` names
this `combined_concentration_ratio` to keep them visibly distinct.

## 3. Composite formula

```
RRS = 0.35 * woa_progress_score
    + 0.30 * rsp_score
    + 0.20 * fm_score
    + 0.10 * lcr_score
    + 0.05 * cri_score
```

Displayed rounded to the nearest whole number (Section 25.1: "0-100 composite score"); every
component score, its weight, and the raw metric behind it must remain visible alongside the
composite (Section 25.1: "must show the component scores, weights, normalization logic").

## 4. Hard-constraint override

Section 25.1: "The score must not conceal failed hard constraints. If the plan fails the
longevity or essential-spending test, the dashboard must show that failure even if the
composite score is high."

The RRS result therefore carries a `hard_constraint_failed: bool` and
`hard_constraint_detail: str | None` alongside the numeric score, evaluated via the existing
`retirement_tests.longevity_test`/`spending_test` at the same date the components are computed.
A failing longevity or spending test does **not** zero out the numeric RRS (the number itself
stays informational, per Section 25.1's framing that it must not *conceal* the failure, not
that the number itself must change) -- instead the caller-facing contract is: **always check
`hard_constraint_failed` and display it prominently regardless of the RRS value**, exactly the
way a future dashboard would render a red banner over an otherwise-plausible-looking score.
When WOA is Not Achievable, `hard_constraint_failed` is forced `True` (Not Achievable is itself
a failure of the same underlying tests, evaluated across the entire search window) and
`woa_progress_score` is forced to `0` per Section 2.1.

## 5. Assumption-confidence adjustment

Section 25.1/27: the application "must show... the assumption-confidence adjustment," and
Section 27 requires "an aggregate model-confidence indicator without replacing the underlying
retirement metrics" -- i.e., confidence is reported *alongside* RRS, not blended into it.

`retirement_readiness.py` computes an aggregate confidence percentage from every material
`Valued`/placeholder input already flagged Confirmed/Assumption/Placeholder/Estimated/Derived
elsewhere in the engine: each account's `annual_return`, each liquidity event's `tax_rate`,
each real-estate entry's `appreciation_rate`, the equity position's price-path anchors, the
mortgage payoff plan's placeholder flag, and the two universal tax placeholders
(`PRE_RETIREMENT_EFFECTIVE_TAX_RATE`, `tax.TAX_DEFERRED_DISTRIBUTION_TAX_RATE`). Per-status
weights are an engine-author assumption (the PRD gives the status taxonomy but no numeric
confidence weights):

| Status | Weight |
|---|---|
| Confirmed | 1.00 |
| Derived | 1.00 |
| Assumption | 0.70 |
| Estimated | 0.50 |
| Placeholder | 0.30 |

```
confidence_percent = 100 * mean(weight(status) for each material input)
```

This is a simple unweighted mean across inputs (not weighted by dollar materiality), a
deliberate simplification flagged here rather than silently assumed: a $100,000 placeholder
and a $10 placeholder currently count equally. Materiality-weighting is a reasonable future
refinement, not implemented in this pass.

## 6. Worked example (baseline scenario)

Computed against the baseline scenario's own solved values (Phase 2-4), at its Monte
Carlo-verified WOA of 2055-01-01:

| Component | Raw value | Score |
|---|---|---|
| WOA progress | WOA 2055-01-01; search window 2026-01-01 to 2066-01-01 | 27.5 |
| RSP | success probability 90.9% vs. 90% threshold | 100 |
| Freedom Margin | FM ratio +155.6% (clamped) | 100 |
| Liquidity Coverage | 15.2 years vs. 4-year (2x reserve) target | 100 |
| Concentration Risk | 22.2% combined equity+real-estate exposure | 77.8 |

```
RRS = 0.35*27.5 + 0.30*100 + 0.20*100 + 0.10*100 + 0.05*77.8
    = 9.6 + 30.0 + 20.0 + 10.0 + 3.9
    = 73.5
```

`hard_constraint_failed = False` (both deterministic tests pass at the solved WOA, by
construction of the solver itself). `confidence_percent = 53.1%` -- unsurprising given the
baseline's own liquidity-event tax rates, real-estate appreciation rates, and the 2030 equity
price anchor are all flagged `Placeholder`/`Assumption` pending real confirmation (Section 4).
(This figure moved slightly from the 51.7% originally computed in this document, once Phase 5
added a zero-balance `"roth"` account to the baseline seed -- one more `Assumption`-status
input in the confidence aggregate, with no effect on any dollar figure.) This number is
exercised as a golden-style test in `tests/test_retirement_readiness.py` so a future change to
any component's formula is visible as a deliberate, reviewed diff rather than a silent drift.

## 7. Explicitly out of scope for this pass

- Individual-security concentration (Section 25's third CRI input) -- not modeled, no such
  entity exists yet.
- Materiality-weighted confidence (dollar-weighted rather than input-count-weighted).
- Per-component configurability of the normalization *curves* themselves (only the composite
  *weights* are scenario-configurable in this pass; the curves in Sections 2.1-2.5 are fixed
  constants). Section 25.1 requires the weights be configurable and transparent; it does not
  require the curves themselves be configurable.
