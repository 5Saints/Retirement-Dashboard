# FIOS Delivery Plan

Reproduces PRD Section 21's phased delivery plan with a status column. Per Clarification Log
CL-6, no implementation-time/cost estimate is provided — development is performed with Claude
Code, where an effort estimate serves no scheduling function. Each phase is its own review
checkpoint: it is designed, implemented, tested against its exit criteria, and reviewed with the
user before the next phase begins.

| Phase | Deliverable | Exit Criteria | Status |
|---|---|---|---|
| 1. Core engine | Data model, deterministic projection, baseline scenario, consumption residual | All baseline acceptance tests pass (Section 19) | **In progress (this repo)** |
| 2. WOA and SAS | Candidate-date solver (Section 6.3), spending solver, FID, Freedom Margin, dashboard metrics | WOA, FID, SAS, FM reproducible with trace | Not started |
| 3. Scenario engine | Clone, override, compare, decision evaluation | Side-by-side decisions operational | Not started |
| 4. Monte Carlo | Stochastic returns, inflation, probability outputs | 10,000-run simulation validated | Not started |
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

## Next checkpoint

Before starting Phase 2 (WOA/SAS solver), review with the user: the monotonicity property test
strategy, the coarse-scan/bisection/Monte-Carlo-verification solver contract (Section 6.3), and
performance targets (2s deterministic solve, 45s with Monte Carlo verification).
