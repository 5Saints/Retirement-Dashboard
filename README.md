# FIOS — Financial Independence Operating System

A private, auditable financial-planning application: single source of truth for the household
balance sheet, accumulation/retirement cash-flow projections, Work-Optional Age (WOA), and
deterministic/probabilistic stress tests.

Built from the frozen PRD in `docs/` — see `docs/FIOS_PRD_v2_1.md` if present, or the original
upload, for the full specification. This repo implements the full calculation engine (Section
21's Phases 1-8) plus a minimal API layer wrapping it; see `docs/delivery-plan.md` for the
phased build-out and exactly what each phase covers.

## Pre-implementation deliverables

- [`docs/architecture.md`](docs/architecture.md) — system architecture and the calc-engine/
  API/DB/frontend layering
- [`docs/erd.md`](docs/erd.md) — entity-relationship diagram
- [`docs/calculation-spec.md`](docs/calculation-spec.md) — authoritative formulas and
  processing order (what the Phase 1 tests are written against)
- [`docs/threat-model.md`](docs/threat-model.md) — security threat model
- [`docs/delivery-plan.md`](docs/delivery-plan.md) — phased delivery plan with status
- [`docs/rrs-normalization-spec.md`](docs/rrs-normalization-spec.md) — Retirement Readiness
  Score normalization formulas (pre-4b design deliverable)

## Engine (`engine/`)

```
engine/
  fios_engine/     # pure-Python calculation engine, no web/db/UI dependencies
  tests/           # golden-file + property tests against docs/calculation-spec.md
```

### Running the tests

```bash
cd engine
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest tests/ -v
```

### What's implemented

The full calculation engine: data model, baseline household seed data, company-equity share
ledger and price-path interpolation, anchored-real retirement spending, mortgage payoff-boundary
placeholder, effective-rate tax placeholders, the monthly/annual projection engine, the WOA/SAS
solvers, Monte Carlo simulation, scenario cloning/overrides and a built-in scenario library,
configurable withdrawal strategies and Roth conversions, the Retirement Readiness Score, a
recommendation engine with persisted status/history tracking, Legacy Value/estate projections,
the full Section 14 reporting suite (12 report types, CSV/JSON/Excel/PDF exports), and a manual
valuation-feed adapter. `docs/delivery-plan.md` has a detailed scope note per phase.

### What's not implemented (and why)

Live account aggregation and any credential/OAuth handling are deliberately deferred — Section
3.2 lists live brokerage aggregation as "Deferred or Optional," and it needs the auth/persistence
layer below, which doesn't exist yet.

## API (`api/`) — minimal layer, not the full Section 16 stack

```
api/
  fios_api/        # FastAPI app wrapping fios_engine (Section 17.1 endpoints)
  tests/           # TestClient-based endpoint tests
```

A small FastAPI service exposing Section 17.1's endpoints (`/scenarios/{id}/calculate`,
`/monte-carlo`, `/decisions/evaluate`, `/dashboard`, `/projection`, `/clone`, `/reports`,
`/audit-events`) by wrapping existing engine functions — no calculation logic lives here. See
`docs/architecture.md` for what this is and, more importantly, what it deliberately is not yet:
there is **no real database** (scenarios live in an in-memory store, reset on restart), **no
authentication**, **no frontend**, and **no async job queue** — Monte Carlo and report
generation run synchronously in the request. This is a prototype layer, not a production
deployment.

### Running the API

```bash
cd engine && pip install -e .        # fios_engine must be installed into the same environment
cd ../api && pip install -e ".[dev]"
uvicorn fios_api.main:app --reload
```

### Running the tests

```bash
cd api
pytest tests/ -v
```
