# FIOS Calculation Specification (Phase 1)

This is the authoritative formula reference for the Phase 1 engine. All Phase 1 tests
(`engine/tests/`) are written directly against the worked numbers in this document, which are
themselves taken from PRD Section 19 (Acceptance Criteria) and Appendix A (Baseline Snapshot).

All money values are `decimal.Decimal`. Rounding to the cent happens only when a value is
reported at period close — intermediate arithmetic stays at full precision.

## 1. Baseline Balance Sheet (Section 4.3–4.4, Appendix A)

| Asset | Value |
|---|---|
| Cash | $100,000.00 |
| 401(k) | $575,000.00 |
| Taxable brokerage | $400,000.00 |
| Company equity | 166.122 shares × $21,589.92 = $3,586,560.69 |
| Primary residence | $700,000.00 |
| Lake home | $1,500,000.00 |
| **Total assets** | **$6,861,560.69** |
| Primary mortgage | ($100,000.00) |
| **Net worth** | **$6,861,560.69 − $100,000.00 = $6,761,560.69** |

Company-equity value is *never* an input — it is always `share_quantity × resolve_price(date)`
(see Section 4 below). No standalone dollar value may be stored (Appendix B).

## 2. Salary Projection (Section 4.2)

```
salary(year) = 312_000 * 1.02 ** (year - 2026)
total_comp(year) = salary(year) + 100_000        # bonus is flat, no growth
```

Worked value: `salary(2032) = 312_000 * 1.02**6 = 351,362.61...` → reported as **$351,363**
(nearest dollar); `total_comp(2032) = 451,363`.

## 3. Retirement Spending — Anchored-Real Rule (Section 4.9, CR-003)

The $300,000 spending target is anchored to **2032 dollars**, not 2026. For any candidate
retirement year `Y`:

```
first_year_spending(Y) = 300_000 * (1 + i) ** (Y - 2032)
```

where `i` is the retirement inflation rate (default 3%). After retirement begins, spending grows
at `i` per year from that first-year value. The six category amounts (core $150k, travel $40k,
vehicles $20k, hobbies $20k, home improvements $30k, misc $40k) and the 50/50 essential/
discretionary split scale **proportionally** to `first_year_spending(Y) / 300_000` at any
retirement date. The engine must never inflate $300,000 forward from 2026 to 2032 — 2032 is the
anchor, not the base year.

Worked values (i = 3%):

| Y | Formula | Result |
|---|---|---|
| 2031 | `300_000 * 1.03**-1` | **$291,262** (291,262.1359... rounds to 291,262) |
| 2032 | `300_000 * 1.03**0` | **$300,000** |
| 2033 | `300_000 * 1.03**1` | **$309,000** |

## 4. Company-Equity Price Path (Section 4.7.1)

| Effective Year | Price/Share | Status |
|---|---|---|
| 2026 | $21,589.92 | Confirmed |
| 2027–2029 | pending | Placeholder |
| 2030 | $70,000.00 | Assumption, low confidence |

`resolve_price(date, mode="step")`: find the latest anchor with `effective_date <= date`; return
its price. After the last anchor, price holds flat (no extrapolation). `mode="geometric"`
interpolates compounding growth between the two bracketing anchors; not the default.

Because 2027–2029 anchors are unsupplied, `resolve_price` for any date in that window falls back
to the 2026 anchor under step interpolation until real data is entered — this is the designed
behavior (Section 4.7.1: "the most recent anchor at or before the valuation date applies"), not a
gap to patch.

## 5. Liquidity Events (Section 4.7, Appendix A)

Gross proceeds are **always derived**: `gross = shares_sold * resolve_price(event_date)`. Never
entered directly.

**Event 1** — fixed date 2026-09-30 (placeholder pending exact day), 111.163 shares at the 2026
anchor ($21,589.92). Gross is rounded to the cent immediately on derivation — it is a reported
value, not an intermediate in a longer chain — and tax/net follow from that rounded figure. This
rounding order is what reconciles exactly with the Appendix A worked numbers:

```
gross (full precision) = 111.163 * 21_589.92  = 2,400,000.27696
gross (rounded)         = $2,400,000.28
tax    = round(gross * 0.30, cents)           = $720,000.08
net    = gross - tax                          = $1,680,000.20
re_alloc   = $500,000.00 (fixed allocation to real estate)
invested   = net - re_alloc                   = $1,180,000.20
shares_remaining = 166.122 - 111.163          = 54.959
```

**Event 2** — retirement-linked (CR-005): defaults to the scenario's candidate retirement date,
selling all remaining shares (54.959 at baseline) at the price anchor prevailing on that date. In
the baseline scenario (retirement 2032, but anchor table stops at 2030 and holds flat), the
2030 anchor of $70,000 applies:

```
gross      = 54.959 * 70_000             = $3,847,130.00
tax        = gross * 0.30                = $1,154,139.00
invested   = gross - tax                 = $2,692,991.00
shares_remaining = 0
```

After Event 2, Concentration Risk Index (equity component) = 0.

Tax rates (30% for both events, 25% for tax-deferred distributions) are effective-rate
placeholders pending CPA confirmation (Section 7.4, CL-2) — flagged, not hidden.

A **2028 candidate retirement date** prices Event 2 (retirement-linked) at whatever anchor
`resolve_price(2028-XX-XX)` returns under step interpolation — with only the 2026 and 2030
anchors populated, this resolves to the 2026 price ($21,589.92) until 2027–2029 anchors are
supplied. This exercises the mechanism required by Section 19's "prices at the 2028 anchor"
acceptance test.

## 6. Mortgage Payoff Boundary (Section 4.10, CR-002)

The $100,000 primary-residence mortgage has no supplied rate/payment/maturity. Placeholder rule:
the balance is modeled as linearly extinguished from the consumption residual by **2031-12-31**
(one year before the 2032 retirement date), flagged as a placeholder in engine output. If real
terms are later supplied and would carry a balance past the retirement date, the engine raises a
warning rather than silently extending the payoff (per CR-002).

## 7. Pre-Retirement Consumption Residual (Section 4.10, CR-002)

Pre-retirement household spending is never an input. It is derived each period as:

```
implied_spending = gross_income - estimated_taxes - 401k_contributions - debt_service
                    - user_activated_taxable_contributions
```

This applies **only** to salary and bonus income. Liquidity-event proceeds never fund
consumption — they follow their allocation rules exclusively (real-estate allocation / invested
proceeds). The conservation identity that must hold every pre-retirement period:

```
income == taxes + contributions + debt_service + implied_spending
```

`implied_spending` is displayed as "Implied Pre-Retirement Spending," classified `derived`, and
used nowhere else as an input (it is a plausibility check only).

## 8. Period Processing Order (Section 7.2)

Each period (monthly through 5 years post-retirement, annual thereafter — Section 7.1) applies,
in order:

1. Open with prior period's closing balances.
2. Apply salary, bonus, pension, Social Security, other income.
3. Calculate payroll and income-tax estimates.
4. Apply spending and debt payments (pre-retirement spending = consumption residual, Section 7).
5. Apply contributions and liquidity-event allocations.
6. Apply investment returns and asset-specific tax drag.
7. Apply real-estate appreciation, income, expenses, and debt amortization.
8. Calculate closing balances, net worth, investable assets, estate value, and metrics
   (including Implied Pre-Retirement Spending during accumulation periods).

## 9. Default Return/Inflation Assumptions (Section 7.3)

- 401(k), taxable portfolio, invested liquidity-event proceeds: 6% nominal accumulation return.
- Post-retirement balanced return: 6% nominal (stress cases 4%/8%, not Phase 1).
- Retirement inflation: 3% default, configurable.

## 10. Metrics (Section 5, Section 25)

- **Net Worth** = total assets (including real estate and company equity) − total liabilities.
- **Investable Assets** = cash + taxable + retirement accounts + liquidated company equity
  (excludes personal-use real estate unless a scenario elects sale).
- **Concentration Risk Index (equity component)** = company-equity value ÷ net worth, and
  separately ÷ investable assets (both shown). Reads 0 once all shares are liquidated.

## Not covered by this spec (later phases)

WOA/SAS solver (Section 6), Monte Carlo (Section 9), tax brackets (Section 7.4 beyond effective
rates), withdrawal sequencing (Section 7.5), scenario overrides (Section 8), and recommendations
(Section 26).
