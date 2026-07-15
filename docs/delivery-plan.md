# FIOS Delivery Plan

Reproduces PRD Section 21's phased delivery plan with a status column. Per Clarification Log
CL-6, no implementation-time/cost estimate is provided — development is performed with Claude
Code, where an effort estimate serves no scheduling function. Each phase is its own review
checkpoint: it is designed, implemented, tested against its exit criteria, and reviewed with the
user before the next phase begins.

| Phase | Deliverable | Exit Criteria | Status |
|---|---|---|---|
| 1. Core engine | Data model, deterministic projection, baseline scenario, consumption residual | All baseline acceptance tests pass (Section 19) | **Done** |
| 2. WOA and SAS | Candidate-date solver (Section 6.3), spending solver, FID, Freedom Margin, dashboard metrics | WOA, FID, SAS, FM reproducible with trace | **Done -- Monte Carlo step deferred to Phase 4 (see scope note)** |
| 3. Scenario engine | Clone, override, compare, decision evaluation | Side-by-side decisions operational | **Done -- see scope note** |
| 4. Monte Carlo | Stochastic returns, inflation, probability outputs | 10,000-run simulation validated | **Done -- see scope note** |
| 4b. Readiness Score | RRS composite, component display, normalization logic, hard-constraint override | Score reproducible; components visible; failed longevity/essential-spending test forces failure display | Not started |
| 5. Tax and withdrawal | Withdrawal sequencing, Roth conversion, tax layers | Tax assumptions visible and testable | Not started |
| 6a. Recommendation engine: generation | Candidate generation, ranking, full Section 26 output fields | Top-five ranked recommendations with explanations and traces | Not started |
| 6b. Recommendation engine: history | Statuses, user responses, realized-impact tracking (Section 26.1) | History persisted and queryable | Not started |
| 7. Legacy and reporting | Estate projections and polished reports | PDF/Excel/CSV exports complete | Not started |
| 8. Integrations | Optional account aggregation and valuation feeds | User-authorized and security-reviewed | Not started |

## Phase 1 scope note

Phase 1 as delivered in this pass implements: the data model (`fios_engine/models.py`), the
baseline household seed (`fios_engine/seed.py`), the share-ledger and price-path mechanics
(`fios_engine/equity.py`), the anchored-real spending rule (`fios_engine/spending.py`), the
mortgage payoff-boundary placeholder (`fios_engine/mortgage.py`), effective-rate tax placeholders
(`fios_engine/tax.py`), and the monthly/annual projection loop with the consumption-residual rule
and net worth/concentration metrics (`fios_engine/projection.py`, `fios_engine/metrics.py`).

It deliberately does **not** implement: the API layer, database persistence, frontend, the WOA/
SAS solver, Monte Carlo, scenario cloning/overrides, tax brackets, withdrawal sequencing,
recommendations, or auth/security infrastructure — those are Phases 2–8 and each needs its own
design/approval pass, per the PRD's own phased structure and the risk of an unreviewable
all-at-once build for a financial-correctness-critical system.

## Phase 2 scope note

Phase 2 as delivered in this pass implements: the Section 6.2 WOA thresholds as `Scenario`
fields (`fios_engine/models.py`), the Section 6.1 required tests (`fios_engine/retirement_tests.py`),
the Section 6.3 solver sequence's coarse-scan-plus-bisection steps and the "Not Achievable"
terminal case (`fios_engine/woa_solver.py`), the Sustainable Annual Spending bisection solver
(`fios_engine/sas_solver.py`), and a dashboard-ready bundle of WOA/FID/SAS/Freedom Margin
(`fios_engine/dashboard.py`). `run_projection` (`fios_engine/projection.py`) gained optional
candidate-retirement-date, candidate-spending-schedule, and return-haircut parameters so the
solvers can evaluate a candidate without mutating the household's own planned retirement date
or the Section 4.9 anchored spending schedule.

Deterministic WOA solve for the baseline scenario runs in well under the 2-second target
(~0.3s measured); the deterministic solver found the baseline's own $300,000 real spending
target is *not* sustainable at the planned 2032 (age 59) retirement over a 36-year horizon to
the Section 6.2 terminal age of 95 -- the solved WOA lands at 2048 instead, and SAS at the
2032 date is ~$267k rather than $300k. Both are exercised by golden-style tests
(`tests/test_retirement_tests.py`, `tests/test_woa_solver.py`, `tests/test_sas_solver.py`) so
this isn't a silent surprise. A property-based test (`tests/test_monotonicity.py`) covers the
Section 6.3 monotonicity invariant the bisection step depends on.

It deliberately does **not** implement Section 6.3 steps 3-4 (Monte Carlo verification): that
needs Phase 4's Monte Carlo engine, which doesn't exist yet. `WOAResult.monte_carlo_verified`
is explicitly `False` and `WOAResult.status` is `Status.PLACEHOLDER` rather than silently
reporting a verified result. The Section 6.1 "stress test" is implemented as a deterministic
proxy only: it reruns the candidate with a flat return haircut reproducing Section 7.3's 4%
post-retirement stress case (`Scenario.stress_return_haircut`), not the full Section 8.1
"Conservative returns" built-in scenario (which needs the Phase 3 scenario-clone engine) or
the Monte Carlo Success Threshold gate (Phase 4). It also does not implement scenario
cloning/overrides, tax brackets, withdrawal sequencing beyond the existing cash/taxable/401k
order, recommendations, or auth/security infrastructure -- those remain Phases 3-8.

## Phase 3 scope note

Phase 3 as delivered in this pass implements: the scenario clone/override primitive
(`fios_engine/scenario_engine.py`, `clone_scenario`/`record_change`, Section 8's "immutable set
of assumptions derived from a parent" plus the Section 28 audit-trail fields on
`Scenario.changes`); a `Decision` entity (Section 11) with real-estate-purchase, real-estate-sale,
and spending-adjustment types injected into the monthly loop the same way liquidity events
already are (`fios_engine/models.py`, `fios_engine/projection.py`); the Section 8.1/28 built-in
scenarios and named templates (`fios_engine/scenario_library.py`: conservative/expected/optimistic
returns, high inflation, higher tax on company payouts, lower company payout, a partial market-
decline scenario, `retire_at_age` covering all of "retire now/57/58/59" and "retire N years
earlier/later", reduce discretionary spending, increase spending, purchase additional real
estate, emergency lake-home sale); and Section 8.2's Decision Output comparison
(`fios_engine/comparison.py`: WOA impact, SAS impact, liquidity impact, legacy impact at ages
75/85/95, tax impact, risk impact, and a "What changed?" summary over the recorded assumption
edits plus the WOA/FID/SAS/FM deltas).

A load-bearing subtlety surfaced while building this: `solve_woa` searches every candidate date
independent of `household.planned_retirement_age`, so comparing two scenarios by always
re-solving WOA on both sides makes every retirement-timing decision (e.g. `retire_at_age`) a
no-op -- the solver just rediscovers the same optimum regardless of the planned age. `snapshot`
therefore accepts an explicit `retirement_date` to evaluate a scenario at a *fixed* date instead
of re-solving; `compare_scenarios` exposes `baseline_retirement_date`/`alternative_retirement_date`
so a caller comparing a timing decision passes
`alternative_retirement_date=alternative.household.retirement_date`. Comparisons of an
assumption-only scenario (returns, inflation, tax, spending scale) should leave both dates
unset, letting WOA re-solve on each side -- that is the correct question for those ("how does
this change move my achievable WOA?"). `tests/test_comparison.py` covers both cases explicitly
so this distinction doesn't silently regress.

A second, unrelated fix landed alongside this work: `tests/test_monotonicity.py` (Phase 2)
intermittently failed on a boundary case where a multi-decade projection's Decimal arithmetic
(28-digit context precision) left a sub-cent (~1e-23) spending shortfall at the razor's-edge
pass/fail boundary -- not a real monotonicity violation. `_withdraw_for_spending`
(`fios_engine/projection.py`) now treats a shortfall at or below one cent as fully funded,
consistent with the engine's existing cents-based reporting convention (`money.py`).

It deliberately does **not** implement: the full "Immediate 25% market decline... extended to
shock the company-equity price path alongside the portfolio" scenario (Section 8.1) -- the
`market_decline` builder only shocks the equity price path (the mechanism this engine already
has); shocking account balances too needs a new projection-engine concept (a balance-level shock
event at an arbitrary date) that doesn't exist yet. It also does not implement the Section 8.2
"Success probability: before and after" output (needs Phase 4 Monte Carlo -- reported as
`None`/`Status.PLACEHOLDER`), the Retirement Readiness Score or RSP components of the "What
changed?" summary (Phase 4b/5), scenario persistence/versioning beyond the in-memory
`AssumptionChange` log (no DB/API layer exists yet), or Roth-conversion/withdrawal-sequencing
decision types.

## Phase 4 scope note

Phase 4 as delivered in this pass implements `fios_engine/monte_carlo.py`: correlated
stochastic annual returns and inflation, a deterministic backbone (liquidity-event proceeds,
401(k) contributions -- both return/inflation-independent per Section 9's own equity-price-path
carve-out) computed once rather than resimulated per path, and the required outputs (success
probability, median terminal balance, 10th/25th/75th/90th percentiles, depletion-age list,
minimum-portfolio-balance median). It wires Section 6.3 steps 3-4 into `woa_solver.solve_woa`
(Monte Carlo verification at the earliest deterministic-passing candidate, stepping forward
monthly on failure until the success threshold clears or the search boundary is reached), and
surfaces success probability on `DashboardSummary` and `comparison.ScenarioComparison`
(`Scenario.monte_carlo_enabled=False` skips Monte Carlo entirely for a fast deterministic-only
path, reporting `Status.PLACEHOLDER` the same way Phase 2 did before this phase existed).

**The Decimal-vs-performance tradeoff was discussed with the user before implementation**
(Section 11 requires Decimal, "never floating-point," everywhere; Section 9/20 requires 10,000
simulations under 15 seconds, which is not achievable in pure-Python Decimal arithmetic at this
scale). The user chose `numpy` float64 arrays scoped to `monte_carlo.py` only -- confirmed,
not assumed. The deterministic engine (`projection.py` and everything built on it) is completely
unaffected and stays pure Decimal; `numpy` is now a declared dependency (`pyproject.toml`),
used nowhere else. Measured performance: 10,000 simulations in ~0.06s (vs. the 15s target), a
full `solve_woa` call including Monte Carlo verification in ~5s (vs. the 45s target).

Capital-market assumptions -- return/inflation standard deviations and their correlation -- are
not given numerically anywhere in the PRD (Section 7.3 gives only point estimates), so
`monte_carlo.py`'s `PORTFOLIO_RETURN_STDEV`/`INFLATION_STDEV`/`RETURN_INFLATION_CORRELATION`
constants are engine-author assumptions, flagged the same way Phase 1 flagged its tax and
mortgage placeholders. Both non-cash accounts (taxable, 401(k)) share one stochastic "portfolio
return" factor rather than independent asset-class draws, since every scenario built so far
gives them the same point-estimate return -- there is no differentiated asset-class data yet.

**Resolved from the Phase 3 checkpoint:** wiring Monte Carlo into the WOA solver surfaced that
an *absolute* conservative-scenario floor for `retirement_tests.stress_test` (tried first, using
`scenario_library.conservative_returns` directly) makes every scenario at or above the 4% floor
collapse to the identical solved WOA regardless of its own return assumption -- since the stress
gate would always bind at exactly 4%, the Phase 3 return-variant scenarios (conservative/
expected/optimistic) would become meaningless for WOA comparison. `Scenario.stress_return_haircut`
was kept (not replaced) for exactly this reason: it is applied *relative to each scenario's own*
return, preserving differentiation. `scenario_library.conservative_returns` remains available
separately for an explicit "what if returns come in at exactly 4%" comparison. See
`models.Scenario`'s docstring and `retirement_tests.stress_test` for the full reasoning.

**Also resolved:** Phase 3's `success_probability_before`/`success_probability_after` (previously
`None`/`Status.PLACEHOLDER`) are now populated by real Monte Carlo runs in `comparison.py`.

**A real, previously-undiscovered bug was found via the Section 20 Monte Carlo boundary tests**
(specifically, trying to force a "certain depletion" boundary case by inflating expense-category
anchors and observing zero effect on the result): `spending.first_year_spending`/`build_schedule`
computed the household's actual retirement spending target from a hardcoded `ANCHOR_TOTAL =
Decimal("300000")` module constant, completely decoupled from `household.expense_categories`.
This meant `scenario_library.reduce_discretionary_spending` and any future spending-increase
decision silently had **no effect** on simulated withdrawals -- only on the essential/
discretionary *ratio* used by the liquidity test, never on the total dollar amount actually
withdrawn. Fixed by deriving the anchor total from `sum(category.anchor_amount for category in
categories)` instead of the constant; every call site (`projection.py`, `woa_solver.py`,
`sas_solver.py`, `dashboard.py`, `comparison.py`, `monte_carlo.py`) now passes the household's
own `expense_categories` through. This is exactly the kind of gap Section 20's boundary-test
requirement exists to catch.

It deliberately does **not** implement: variable longevity or healthcare shocks ("in later
phases" per Section 9 itself), correlated *multi*-asset-class returns (only one shared portfolio
factor, see above), or the Retirement Readiness Score's probability component (Phase 4b, next).

## Next checkpoint

Before starting Phase 4b (Retirement Readiness Score), review with the user: the RRS
normalization specification (Section 23 explicitly requires this as a design document before
4b begins), the component weighting (Section 25.1), and the hard-constraint override behavior
when longevity/essential-spending tests fail.
