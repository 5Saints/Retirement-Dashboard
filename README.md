# FIOS — Financial Independence Operating System

A private, auditable financial-planning application: single source of truth for the household
balance sheet, accumulation/retirement cash-flow projections, Work-Optional Age (WOA), and
deterministic/probabilistic stress tests.

Built from the frozen PRD in `docs/` — see `docs/FIOS_PRD_v2_1.md` if present, or the original
upload, for the full specification. This repo currently implements **Phase 1: Core engine**
only; see `docs/delivery-plan.md` for the full phased build-out.

## Pre-implementation deliverables

- [`docs/architecture.md`](docs/architecture.md) — system architecture and the calc-engine/
  API/DB/frontend layering
- [`docs/erd.md`](docs/erd.md) — entity-relationship diagram
- [`docs/calculation-spec.md`](docs/calculation-spec.md) — authoritative formulas and
  processing order (what the Phase 1 tests are written against)
- [`docs/threat-model.md`](docs/threat-model.md) — security threat model
- [`docs/delivery-plan.md`](docs/delivery-plan.md) — phased delivery plan with status

## Engine (Phase 1)

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

Data model, baseline household seed data, company-equity share ledger and price-path
interpolation, anchored-real retirement spending, mortgage payoff-boundary placeholder,
effective-rate tax placeholders, and the monthly/annual projection engine with the
consumption-residual rule and net worth/concentration metrics.

### What's not yet implemented

API layer, database persistence, frontend, the WOA/SAS solver, Monte Carlo simulation,
scenario cloning/overrides, bracket-based taxes, withdrawal-strategy guardrails,
recommendations, and auth/security infrastructure. See `docs/delivery-plan.md` for the phase
each belongs to.
