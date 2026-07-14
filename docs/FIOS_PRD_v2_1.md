**FINANCIAL INDEPENDENCE OPERATING SYSTEM (FIOS)**

Frozen Product Requirements Document, Discovery Summary, and Baseline Financial Specification

**STATUS: REQUIREMENTS FROZEN — Version 2.1 incorporates approved change requests CR-001 through CR-007 and Clarification Log CL-1 through CL-6 (Appendix C). Future modifications require a documented change request and version increment.**

*Prepared for software-development handoff | Version 2.1 (Requirements Frozen) | July 2026*

| **Primary product question:** If the user stops working on a given date, can the household maintain its desired lifestyle for life while preserving long-term financial objectives? |
|---|

# 1. Executive Summary

Build a private, auditable financial-planning application that maintains a single source of truth for the household balance sheet, projects accumulation and retirement cash flow, calculates a Work-Optional Age (WOA), runs deterministic and probabilistic stress tests, and evaluates major financial decisions. The calculation engine must be independent of the user interface so it can later support a web application, command-line tools, scheduled reports, and Excel/PDF exports.

# 2. Product Objectives

Calculate the earliest age and date at which work becomes optional while maintaining the desired lifestyle with an acceptable probability of success.

Project annual assets, liabilities, income, taxes, spending, and estate value from the present through at least age 100.

Allow users to alter one assumption and immediately see the effect on WOA, sustainable spending, liquidity, Freedom Margin, Retirement Readiness Score, and retirement success probability.

Keep confirmed facts, planning assumptions, and unresolved placeholders clearly separated.

Provide transparent calculations that a financial planner, CPA, or auditor can reproduce.

Protect sensitive financial data through encryption, access controls, audit logs, and secure backups.

# 3. Scope

## 3.1 Included in Version 1

User profile and household configuration

Balance sheet and account inventory

Income and contribution schedules

Company-equity share ledger, price path, and liquidity events

Real-estate tracking

Retirement-spending model

Deterministic accumulation and decumulation projections

WOA calculation

Sustainable Annual Spending (SAS)

Scenario and decision comparison

Basic tax placeholders

Legacy projection (informational only)

Dashboard, reports, and exports

Assumption version history and audit trail

## 3.2 Deferred or Optional

Live brokerage aggregation

Automated tax-return import

Trade execution

Bill payment

Legal-document generation

Personalized securities recommendations

Full tax-return calculation

Estate-document drafting

Insurance underwriting

Automated real-estate valuation

# 4. Baseline Household Financial Data

The following values are the initial production seed data. Every value must be editable, effective-dated, and classified as Confirmed, Assumption, Placeholder, or Derived.

## 4.1 Household and Timeline

| **Field** | **Baseline Value** | **Status** | **Notes** |
|---|---|---|---|
| Current age | 53 | Confirmed | As of 2026 |
| Planned retirement age | 59 | Confirmed | Target retirement year: 2032 |
| Retirement horizon | Age 95 minimum; model through age 100 | Assumption | Configurable |
| Spouse employment income | $0 | Confirmed | Spouse not currently employed |
| Social Security | Excluded from baseline | Confirmed | May be added as optional upside later |
| Investment philosophy | Balanced growth and income | Confirmed | Profile B |

## 4.2 Employment Income

| **Field** | **Baseline Value** | **Status** | **Calculation Rule** |
|---|---|---|---|
| Current salary | $312,000 annually | Confirmed | Base year 2026 |
| Salary increase | 2.0% annually | Confirmed | Compound each year until retirement |
| Annual bonus | $100,000 | Confirmed | No annual growth |
| Projected salary in 2032 | Approximately $351,363 | Derived | $312,000 x 1.02^6 |
| Projected total compensation in 2032 | Approximately $451,363 | Derived | Salary plus bonus |

## 4.3 Current Assets

| **Asset** | **Current Value** | **Liquidity Class** | **Status** |
|---|---|---|---|
| Cash and cash equivalents | $100,000 | Immediate | Confirmed |
| 401(k) | $575,000 | Retirement-restricted | Confirmed |
| Taxable brokerage | $400,000 | Liquid | Confirmed |
| Private company equity (166.122 shares at $21,589.92 per share) | $3,586,560.69 (derived) | Illiquid/concentrated | Shares and current price Confirmed; value Derived |
| Primary residence | $700,000 | Strategic real estate | Confirmed estimate |
| Lake home | $1,500,000 | Emergency/strategic real estate | Confirmed estimate |

Company equity is share-denominated (CR-001). The engine stores share quantity and a price path; dollar value is always derived as shares multiplied by the prevailing price. No standalone dollar valuation of company equity may be entered or stored.

## 4.4 Current Liabilities

| **Liability** | **Balance** | **Status** | **Notes** |
|---|---|---|---|
| Primary residence mortgage | $100,000 | Confirmed | Rate, payment, and maturity not yet supplied; must be fully retired before the retirement date (CR-002) |
| Lake-home mortgage | $0 | Confirmed | Owned free and clear |
| Other debt | $0 assumed | Assumption | Must be editable |

Baseline net worth: $6,761,560.69, calculated as $6,861,560.69 of assets less $100,000 of liabilities. This figure includes illiquid private-company equity and real estate.

## 4.5 401(k) Rules

| **Field** | **Baseline Value** | **Status** | **Implementation** |
|---|---|---|---|
| Starting balance | $575,000 | Confirmed | Opening balance |
| Annual contribution | IRS maximum for applicable year | Confirmed intent | Store annual statutory limits in a configurable table, including the age-50 catch-up and the age 60–63 enhanced catch-up, both applicable within the projection window (CL-3) |
| Employer match | Excluded | Unresolved | Default to $0 until supplied |
| Annual return | 6.0% | Confirmed assumption | Nominal annual return |
| Contribution timing | End-of-year default | Assumption | Allow beginning, monthly, or end-of-year |

## 4.6 Taxable Portfolio Rules

| **Field** | **Baseline Value** | **Status** | **Implementation** |
|---|---|---|---|
| Starting balance | $400,000 | Confirmed | Opening balance |
| Additional regular contributions | $0 | Confirmed current plan | May be activated by scenario |
| Annual return | 6.0% | Confirmed assumption | Nominal annual return |
| Tax drag | Not yet specified | Placeholder | User-configurable by asset type |

## 4.7 Company-Equity Share Ledger and Liquidity Events

Company equity is modeled as a share ledger (CR-001). Each liquidity event specifies shares sold; gross proceeds are derived from the prevailing price-path anchor at the event date. Gross amounts are never entered directly.

| **Event** | **Date Rule** | **Shares Sold** | **Derived Gross** | **Tax Assumption** | **Use of Net Proceeds** |
|---|---|---|---|---|---|
| Event 1 | Fixed: September 2026 (placeholder 2026-09-30 until exact day supplied) | 111.163 | $2,400,000.28 at $21,589.92 | 30% placeholder; unresolved pending CPA | $500,000 allocated to additional real estate; remaining after-tax proceeds invested |
| Event 2 | Retirement-linked: defaults to the scenario retirement date (CR-005) | All remaining (54.959 at baseline) | Shares times prevailing anchor price at event date; $3,847,130 at the $70,000 anchor | 30% placeholder; unresolved pending CPA | Invest after tax into retirement portfolio |

Event 1 derived values at the 30% placeholder: estimated tax $720,000.08; net proceeds $1,680,000.20; real-estate allocation $500,000.00; invested proceeds $1,180,000.20.

Event 2 derived values at the $70,000 anchor and 30% placeholder: estimated tax $1,154,139.00; net invested proceeds $2,692,991.00.

Each liquidity event carries a date_mode of fixed or retirement-linked, and an occurred flag. When an event settles, actual gross, tax withheld, and net proceeds replace the derived values and are reclassified Confirmed (CL-1). A retirement-linked event may be overridden to a fixed date; if a fixed date falls after the retirement date, the concentration test evaluates the gap period explicitly.

When the WOA solver evaluates a candidate retirement date, the retirement-linked event is priced from the price-path anchor applicable to that candidate date, so WOA output reflects both portfolio sufficiency and foregone share appreciation.

### 4.7.1 Company-Equity Price Path

| **Effective Year** | **Price Per Share** | **Status** |
|---|---|---|
| 2026 | $21,589.92 | Confirmed |
| 2027 | To be supplied by user | Placeholder |
| 2028 | To be supplied by user | Placeholder |
| 2029 | To be supplied by user | Placeholder |
| 2030 | $70,000 | Assumption; low confidence |

Interpolation between anchors is a step function by default: the most recent anchor at or before the valuation date applies. Geometric interpolation is a configurable mode. After the last anchor, the price holds flat. The $70,000 anchor implies approximately 34% compound annual appreciation from the 2026 price and must appear in the assumption register as the plan's most aggressive assumption. Anchors are user-editable, effective-dated, and independently confidence-classified; users are expected to update anchors as actual prices are learned.

## 4.8 Real Estate

| **Property** | **Value / Cost** | **Debt** | **Role** | **Baseline Treatment** |
|---|---|---|---|---|
| Primary residence | $700,000 | $100,000 | Residence/legacy | Exclude from retirement income; include in estate |
| Lake home | $1,500,000 | $0 | Emergency liquidity/legacy | Exclude from baseline income; permit emergency-sale scenario |
| Planned additional property | $500,000 purchase allocation | TBD | Strategic investment or residence | Funded from Event 1 proceeds; income and appreciation default to zero until specified |

## 4.9 Retirement Spending

| **Category** | **Annual Amount (2032 anchor)** | **Type** | **Flexibility** |
|---|---|---|---|
| Core living expenses | $150,000 | Essential | Low |
| Travel | $40,000 | Discretionary | High |
| Vehicles | $20,000 | Discretionary/capital reserve | Medium |
| Hobbies | $20,000 | Discretionary | High |
| Home improvements | $30,000 | Discretionary/capital reserve | Medium |
| Miscellaneous | $40,000 | Discretionary | High |
| Total | $300,000 | 2032 actual dollars (anchor) | 50% essential / 50% discretionary |

The spending target is a real level anchored at $300,000 in 2032 dollars (CR-003). For any candidate retirement year Y, first-year spending equals $300,000 multiplied by (1 + i)^(Y − 2032), where i is the configured retirement inflation rate (3% default). Earlier candidates deflate; later candidates inflate. After retirement begins, spending grows at the inflation rate from that first-year value. The essential/discretionary split and the six category amounts scale proportionally at any retirement date. The engine must never inflate the $300,000 from 2026 to 2032; 2032 is the anchor year.

The $300,000 target contains no mortgage debt service (CR-002). Retirement-era housing costs within the target are limited to taxes, insurance, maintenance, and utilities.

## 4.10 Pre-Retirement Cash Flow Rule

Pre-retirement household spending is a derived quantity (CR-002): gross income less estimated taxes, less 401(k) contributions, less debt service, less any user-activated taxable contributions. Cash and taxable balances therefore hold at their opening values plus investment growth and payout allocations, with no incidental savings credited.

The derived figure is computed and displayed each period as "Implied Pre-Retirement Spending," classified Derived in the assumption register, and shown on the dashboard as a plausibility check. It is never used as an input elsewhere.

The consumption residual applies to salary and bonus only. Liquidity-event proceeds are never available for consumption; they follow their allocation rules exclusively.

The primary mortgage must be fully retired before the retirement date. Until rate, payment, and maturity are supplied, the MVP models the $100,000 balance as extinguished from the consumption residual by December 2031, with a visible placeholder flag. When actual terms arrive, the amortization schedule replaces the placeholder and payoff is verified to complete before retirement; if supplied terms would carry a balance past retirement, the engine raises a warning rather than silently extending.

# 5. Core Product Concepts and Definitions

| **Metric** | **Definition** | **Default Rule** |
|---|---|---|
| Work-Optional Age (WOA) | Earliest age/date at which all retirement tests pass | Solved per the strategy in Section 6.3 |
| Sustainable Annual Spending (SAS) | Maximum first-year retirement spending supported under selected constraints | Solved iteratively; nominal dollars in retirement year |
| Investable Assets | Cash, taxable portfolio, retirement accounts, and liquidated company equity | Exclude personal-use real estate unless scenario elects sale |
| Net Worth | Total assets less liabilities | Include real estate and company equity |
| Lifestyle Coverage | Years of essential spending coverable by liquid low-volatility assets | Core spending only |
| Concentration Risk | Percentage of net worth and investable assets in one employer/company | Show both measures |
| Legacy Value | Projected estate value at selected ages | Financial assets plus net real-estate equity less debts |
| Plan Success | Portfolio remains positive through horizon and satisfies configured legacy floor | Monte Carlo and deterministic variants |

# 6. Work-Optional Age Calculation

For every candidate retirement date evaluated, the engine must run the full retirement model. The earliest candidate date that passes every enabled test is the WOA. Candidate evaluation follows the solver strategy in Section 6.3.

## 6.1 Required Tests

Liquidity test: sufficient liquid assets exist to fund at least the configured cash-reserve period without forced real-estate sale.

Longevity test: investable assets remain above zero through the selected terminal age.

Spending test: all essential spending and the selected discretionary budget are funded.

Stress test: the plan passes the configured conservative deterministic scenario and/or the Monte Carlo Success Threshold.

Legacy test: optional and disabled by default. Terminal estate is informational unless the user explicitly enables a legacy floor.

Concentration test: retirement is not dependent on an unsold employer-equity position unless explicitly allowed. Under the retirement-linked liquidation rule (CR-005) the baseline satisfies this test by construction, because the candidate retirement date triggers full liquidation. The test remains active to flag scenarios that override liquidation to a fixed date after retirement.

Tax test: estimated taxes on liquidity events and retirement withdrawals are included.

## 6.2 Default Thresholds

| **Rule** | **Default** | **Configurable** |
|---|---|---|
| Success Threshold (single probability parameter; CR-004) | 90% | Yes |
| Terminal age | 95 | Yes |
| Legacy floor | $0 for MVP | Yes |
| Cash reserve | 24 months of core spending | Yes |
| Maximum initial withdrawal-rate warning | 4.0% | Yes; warning, not sole pass/fail rule |
| Essential-spending guardrail | Must always be funded | Yes |

The Success Threshold is the sole probability parameter in the system. It gates the WOA stress test, appears on the dashboard, and anchors the probability component of the Retirement Readiness Score. No separate display target exists.

## 6.3 WOA Solver Strategy (CR-007)

Monotonicity is asserted as a model invariant: if all enabled tests pass at candidate date D, they pass at every later date. The solver may therefore bisect. A property-based test verifies the invariant against generated scenarios; if a future feature breaks monotonicity, that test fails and the solver strategy must be revisited by change request.

Solver sequence:

1. Coarse annual scan using deterministic tests only, to bracket the earliest passing year.
2. Monthly bisection within the bracket to find the earliest deterministic pass.
3. Monte Carlo verification at that single candidate, if the stress test is enabled.
4. On verification failure, step forward monthly, re-verifying, until pass.

Monte Carlo runs use variance-consistent seeds during solver stepping so adjacent candidates are comparable, per the reproducibility rules in Section 9.

If no candidate passes by the terminal age less the cash-reserve period, the solver returns Not Achievable with the earliest-failing test identified, rather than scanning indefinitely.

Performance targets: deterministic WOA solve under 2 seconds; WOA with Monte Carlo verification under 45 seconds via background execution with progressive dashboard updates.

# 7. Calculation Engine Requirements

## 7.1 Time Resolution

Monthly resolution from current date through five years after retirement; annual resolution thereafter is acceptable for MVP.

All events require exact effective dates.

Cash flows must be applied in a documented order within each period.

The model must support both beginning-of-period and end-of-period cash-flow timing.

## 7.2 Annual/Monthly Processing Order

Begin with opening balances.

Apply salary, bonus, pension, Social Security, and other income.

Calculate payroll and income-tax estimates.

Apply spending and debt payments. Pre-retirement spending is the consumption residual defined in Section 4.10.

Apply contributions and liquidity-event allocations.

Apply investment returns and asset-specific tax drag.

Apply real-estate appreciation, income, expenses, and debt amortization.

Calculate closing balances, net worth, investable assets, estate value, and metrics, including Implied Pre-Retirement Spending during accumulation periods.

## 7.3 Returns and Inflation

Support deterministic returns by account and scenario.

Support stochastic returns using capital-market assumptions, covariance matrices, and inflation distributions.

Separate nominal return, real return, income yield, capital appreciation, fees, and tax drag.

Default accumulation return: 6% for 401(k), taxable portfolio, and invested payout proceeds.

Default post-retirement balanced return: 6% nominal, with stress cases at 4% and 8%.

Default retirement inflation: 3%, configurable.

## 7.4 Tax Model

The MVP tax engine may use effective rates, but the architecture must permit later replacement with a bracket-based federal and state tax module.

Separate ordinary income, qualified dividends, interest, short-term gains, long-term gains, retirement distributions, and company-equity proceeds.

Store tax basis where available.

Support federal, state, payroll, net-investment-income, and property taxes.

Liquidity Event 1: 30% effective-tax placeholder; unresolved pending CPA confirmation.

Liquidity Event 2: 30% effective-tax placeholder; unresolved pending CPA confirmation.

Tax-deferred retirement distributions: 25% effective-tax placeholder; unresolved pending CPA confirmation (CL-2). The state field on the Household entity may inform a revised placeholder before CPA confirmation.

Display gross, estimated tax, and net proceeds separately.

Never hide a tax assumption inside a return assumption.

## 7.5 Withdrawal Strategy

Configurable withdrawal order: cash, taxable, tax-deferred, Roth, real estate.

Allow proportional withdrawals across accounts.

Permit capital-gain realization limits and tax-bracket targets.

Support Roth-conversion scenarios between retirement and required minimum distributions.

Support spending guardrails: full budget, discretionary cuts, and essential-only floor.

Support emergency sale of lake home as an explicit scenario, not an automatic baseline action.

# 8. Scenario and Decision Engine

A scenario is a complete, immutable set of assumptions derived from a parent scenario. A decision is a scenario change with a date, amount, funding source, and optional recurring effect.

## 8.1 Required Built-In Scenarios

Baseline

Conservative returns

Expected returns

Optimistic returns

Immediate 25% market decline at retirement, extended to shock the company-equity price path alongside the portfolio (CR-005), so the stress applies to the full balance sheet rather than the smaller half

High inflation

Lower company payout, reparameterized as a lower price anchor at the liquidation date (CR-001); this is the designated stress vehicle for share-price risk (CR-004)

Higher tax rate on company payouts

Retire one year earlier (spending target per the anchored-real rule, Section 4.9)

Retire one year later (spending target per the anchored-real rule, Section 4.9)

Purchase additional real estate

Reduce discretionary spending

Emergency lake-home sale

All retirement-timing scenarios inherit the retirement-linked liquidation behavior of Section 4.7 with no special casing.

## 8.2 Decision Output

| **Output** | **Requirement** |
|---|---|
| WOA impact | Difference in years and months |
| SAS impact | Dollar and percentage change |
| Success probability | Before and after |
| Liquidity impact | Minimum liquid balance and years of core coverage |
| Legacy impact | Estate-value change at ages 75, 85, 95 |
| Tax impact | Estimated cumulative tax difference |
| Risk impact | Concentration, sequence, and real-estate exposure |

# 9. Monte Carlo and Stress Testing

Minimum 10,000 simulations per scenario for production calculations.

Use reproducible random seeds for test runs.

Support correlated returns across asset classes.

Model inflation independently but with optional correlation to returns.

Support variable longevity and healthcare shocks in later phases.

Report success probability, median outcome, 10th/25th/75th/90th percentiles, depletion age distribution, and minimum portfolio balance.

Never present Monte Carlo probability as a guarantee.

Note: the company-equity price path is deterministic in the MVP simulation; simulation risk applies to portfolio returns and inflation. Share-price risk is stress-tested through the lower-payout and market-decline scenarios (CR-004, CR-005).

# 10. Application Modules

| **Module** | **Primary Functions** |
|---|---|
| Dashboard | WOA, FID, SAS, FM, success probability, RRS, net worth, investable assets, risk flags, key changes; card availability by phase per Section 13 |
| Household | People, ages, life expectancy, employment, Social Security |
| Accounts | Balances, ownership, tax type, allocation, fees, basis, liquidity |
| Income | Salary, bonus, benefits, pension, Social Security, one-time income |
| Spending | Essential/discretionary categories, inflation, start/end dates, guardrails, implied pre-retirement spending |
| Company Equity | Share ledger, price path, liquidity events, taxes, proceeds allocation |
| Real Estate | Value, debt, expenses, income, appreciation, sale scenarios |
| Taxes | Effective-rate assumptions and later detailed tax engine |
| Projection | Year/month financial statements through terminal age |
| Scenarios | Clone, edit, compare, lock, archive |
| Decisions | Enter proposed transaction and view impacts |
| Recommendations | Candidate generation, ranking, explanation, history (CR-006) |
| Scoring | RRS composite, component normalization, confidence adjustment (CR-006) |
| Legacy | Estate values, gifting, charitable goals, legacy floors |
| Reports | PDF/Excel/CSV exports and annual planning report |
| Audit | Change log, user, timestamp, prior value, new value, reason |

# 11. Data Model

Use a relational database or strongly typed document model. Financial amounts should use decimal types, never floating-point types.

| **Entity** | **Key Fields** |
|---|---|
| Household | id, name, state, filing_status, base_currency |
| Person | id, household_id, birth_date, role, retirement_date, life_expectancy |
| Account | id, owner_id, type, tax_treatment, institution, balance, valuation_date, liquidity_class |
| Asset | id, account_id, asset_class, ticker_or_description, value, basis, employer_related |
| EquityPosition | id, household_id, description, share_quantity, basis, employer_related |
| PricePath | id, equity_position_id, effective_date, price, interpolation_mode, status, confidence |
| Liability | id, type, balance, rate, payment, maturity, linked_asset_id, payoff_boundary_rule |
| IncomeStream | id, person_id, type, amount, frequency, start_date, end_date, growth_rate |
| Expense | id, category, essential_flag, anchor_amount, anchor_year, frequency, inflation_rate, start_date, end_date |
| LiquidityEvent | id, equity_position_id, date_mode, date, shares_sold, tax_rule, net_allocation, occurred_flag |
| RealEstate | id, value, debt, income, expenses, appreciation, liquidity_role |
| Assumption | id, key, value, unit, status, effective_date, source, confidence |
| Scenario | id, parent_id, name, created_at, locked_at |
| ScenarioOverride | scenario_id, assumption_id, overridden_value |
| ProjectionResult | scenario_id, period, metric_name, value |
| SimulationRun | scenario_id, seed, iterations, model_version, timestamp |
| Decision | id, scenario_id, type, date, amount, funding_source, recurring_effect |
| Recommendation | id, scenario_id, created_at, model_version, scenario_version, text, action, timing, amount, funding_source, expected_impact, confidence, invalidation_conditions, status |
| RecommendationHistory | recommendation_id, status_change, user_response, realized_impact, timestamp |
| AuditEvent | entity, field, old_value, new_value, user, timestamp, reason |

Liquidity-event gross proceeds are derived (shares_sold multiplied by prevailing PricePath price) and are not stored as inputs.

# 12. User Experience Requirements

Dashboard must answer the primary question without requiring navigation.

Every metric must include a plain-language definition and an assumptions link.

Confirmed facts, assumptions, placeholders, and derived values must use distinct visual states.

Changing an input must show affected outputs and a before/after comparison.

The system must preserve a baseline scenario that cannot be overwritten accidentally.

Users must be able to clone a scenario before editing.

All charts must expose underlying values in tables.

Reports must display model date, scenario name, assumptions, and model version.

The application must support desktop screens first; mobile view may be read-only in MVP.

# 13. Dashboard Requirements

| **Card / Widget** | **Content** | **Available From Phase** |
|---|---|---|
| Primary answer | Can retire today: Yes/No; WOA date and age | 2 |
| WOA / FID | Age, date, change since prior snapshot | 2 |
| SAS | Conservative, baseline, and optimistic annual spending | 2 |
| Freedom Margin | SAS minus desired spending at the evaluated date | 2 |
| Success probability | Baseline and stress-tested | 4 |
| Retirement Readiness Score | Composite with visible components | 4b |
| Net worth | Current and projected at retirement | 2 |
| Investable assets | Current and projected at retirement | 2 |
| Liquidity | Years of essential spending covered | 2 |
| Implied pre-retirement spending | Derived plausibility check per Section 4.10 | 1 |
| Concentration | Company equity as % of net worth and investable assets, from the share ledger and price path | 2 |
| Legacy | Projected estate at ages 75, 85, and 95 | 7 |
| Risk alerts | Tax placeholders, price-anchor uncertainty, concentration, sequence risk | 2 |
| Next best action | Highest-priority unresolved input or decision | 6a |

# 14. Reporting Requirements

One-page executive summary

Full annual projection table

Balance sheet

Cash-flow statement

Asset-allocation report

Company-equity ledger and event schedule

Retirement-income sources

Scenario-comparison report

Monte Carlo report

Legacy report (informational)

Assumption register

Audit/change report

Exports: PDF for presentation, Excel for audit and custom analysis, CSV/JSON for data portability.

# 15. Security and Privacy

Encrypt data in transit and at rest.

Use multi-factor authentication.

Support role-based access: owner, spouse, advisor, read-only professional.

Maintain immutable audit logs for financial-data changes.

Do not store account passwords or brokerage credentials in application tables.

Use a secrets manager for API keys.

Support full data export and permanent deletion.

Automatic session timeout and device/session management.

Backups must be encrypted, versioned, and restoration-tested.

Production logs must not contain balances, tax IDs, account numbers, or credentials.

# 16. Technical Architecture

Recommended architecture: a deterministic Python calculation library, a separate API layer, a relational database, a web frontend, and asynchronous workers for Monte Carlo simulations and report generation.

| **Layer** | **Recommendation** | **Requirement** |
|---|---|---|
| Calculation engine | Python package | Pure functions where possible; independently testable |
| API | FastAPI or equivalent | Versioned REST/JSON endpoints |
| Database | PostgreSQL | Decimal financial types; migrations; point-in-time backups |
| Frontend | React/TypeScript or equivalent | Typed API client; scenario comparison UI |
| Jobs | Celery/RQ/managed queue | Monte Carlo and report generation |
| Authentication | Managed identity provider | MFA and role-based access |
| Deployment | Containerized cloud environment | Separate dev/test/prod |
| Observability | Structured logs, metrics, error tracing | No sensitive values in logs |

The calculation engine must not depend on the web framework, database ORM, or UI. It should accept a validated scenario object and return a complete result object.

# 17. Calculation API Contract

Minimum engine input: household profile, opening balance sheet, income streams, expense streams, equity positions and price paths, liquidity events, account rules, tax assumptions, return assumptions, scenario configuration, and terminal constraints.

Minimum engine output: period-by-period cash flow and balances, WOA, FID, SAS, Freedom Margin, pass/fail tests, risk metrics, legacy values (informational only), warnings, and a complete calculation trace.

## 17.1 Required Endpoints

POST /scenarios/{id}/calculate

POST /scenarios/{id}/monte-carlo

POST /scenarios/{id}/decisions/evaluate

GET /scenarios/{id}/dashboard

GET /scenarios/{id}/projection

POST /scenarios/{id}/clone

POST /reports

GET /audit-events

# 18. Auditability and Explainability

Every output must be traceable to inputs and formulas.

Store model version and assumption version with each run.

Provide a calculation-trace view for any year and account.

Identify unresolved placeholders prominently.

Do not silently replace missing data with defaults; defaults must be logged and displayed.

Allow deterministic runs to be reproduced exactly.

Regression-test baseline outputs whenever the engine changes.

# 19. Acceptance Criteria

The seeded baseline balance sheet calculates total assets of $6,861,560.69, liabilities of $100,000, and net worth of $6,761,560.69, with company-equity value derived as 166.122 shares at $21,589.92.

The salary engine calculates approximately $351,363 salary and $451,363 total compensation in 2032.

Liquidity Event 1 derives gross proceeds of $2,400,000.28 from 111.163 shares at $21,589.92, calculates $720,000.08 estimated tax at 30%, $1,680,000.20 net proceeds, $500,000.00 real-estate allocation, and $1,180,000.20 invested proceeds.

After Event 1, the share ledger holds exactly 54.959 shares.

Liquidity Event 2 in the baseline derives gross proceeds of $3,847,130.00 from 54.959 shares at the $70,000 anchor, calculates $1,154,139.00 estimated tax at 30%, and $2,692,991.00 net invested proceeds. After Event 2, the share ledger holds zero shares and the Concentration Risk Index reads zero.

A candidate retirement date of 2028 prices the retirement-linked liquidation at the 2028 price anchor.

The retirement-spending engine yields exactly $300,000 first-year spending for a 2032 retirement, $291,262 for a 2031 candidate, and $309,000 for a 2033 candidate, and applies inflation only after retirement begins.

In the baseline, liabilities equal $0 at the retirement date, and the conservation identity income = taxes + contributions + debt service + implied spending holds in every pre-retirement period.

The system calculates WOA per the solver strategy in Section 6.3, and bisection agrees with an exhaustive scan on a reference scenario.

WOA output responds to changes in the single Success Threshold, verifying that one parameter drives the stress-test gate, the dashboard display, and the RRS probability component.

A user can clone the baseline scenario, change one value, calculate, and see side-by-side WOA, FID, SAS, probability, liquidity, tax, Freedom Margin, Retirement Readiness Score, and informational estate impacts.

Every displayed result provides access to assumptions and calculation trace.

No sensitive financial value appears in application logs.

Automated tests cover financial formulas, date handling, taxes, contributions, event timing, withdrawals, and scenario inheritance.

# 20. Testing Requirements

Unit tests for every financial formula and timing convention.

Golden-file tests for the seeded baseline scenario.

Property-based tests for conservation of cash and balance consistency, enabled by the Section 4.10 consumption-residual rule.

Property-based test for WOA monotonicity per Section 6.3.

Boundary test for the Not Achievable solver outcome.

Monte Carlo distribution sanity checks.

Boundary tests for zero returns, negative returns, high inflation, depletion, and terminal-age handling.

Database migration tests.

API contract tests.

Security tests for authentication, authorization, injection, secrets, and data export/deletion.

Performance targets: deterministic single-run calculation under 500 ms; 10,000-run Monte Carlo under 15 seconds using background execution; deterministic WOA solve under 2 seconds; WOA with Monte Carlo verification under 45 seconds.

# 21. Phased Delivery Plan

| **Phase** | **Deliverable** | **Exit Criteria** |
|---|---|---|
| 1. Core engine | Data model, deterministic projection, baseline scenario, consumption residual | All baseline acceptance tests pass |
| 2. WOA and SAS | Candidate-date solver per Section 6.3, spending solver, FID, Freedom Margin, dashboard metrics | WOA, FID, SAS, and FM reproducible with trace |
| 3. Scenario engine | Clone, override, compare, decision evaluation | Side-by-side decisions operational |
| 4. Monte Carlo | Stochastic returns, inflation, probability outputs | 10,000-run simulation validated |
| 4b. Readiness Score | RRS composite, component display, normalization logic, hard-constraint override | Score reproducible; components visible; failed longevity or essential-spending test forces failure display regardless of composite |
| 5. Tax and withdrawal | Withdrawal sequencing, Roth conversion, tax layers | Tax assumptions visible and testable |
| 6a. Recommendation engine: generation | Candidate generation, ranking, full Section 26 output fields | Top-five ranked recommendations with explanations and traces |
| 6b. Recommendation engine: history | Statuses, user responses, realized-impact tracking per Section 26.1 | History persisted and queryable |
| 7. Legacy and reporting | Estate projections and polished reports | PDF/Excel/CSV exports complete |
| 8. Integrations | Optional account aggregation and valuation feeds | User-authorized and security-reviewed |

# 22. Known Open Items

| **Item** | **Current Default** | **Why Needed** |
|---|---|---|
| Exact date of the September 2026 share sale | 2026-09-30 placeholder | Event timing precision; occurred flag set at settlement |
| Price anchors for 2027, 2028, 2029 | Pending from user | Required for pricing early-retirement candidates |
| Employer 401(k) match | $0 | Affects retirement-account accumulation |
| 401(k) contribution timing | End of year | Changes projected balance slightly |
| 401(k) statutory limit table with catch-up amounts | To be seeded | Age-50 and age 60–63 catch-ups apply within the window |
| Primary mortgage rate/payment/maturity | Payoff-by-2031 placeholder | Exact payoff date within pre-retirement window |
| Event 1 tax treatment | 30% effective rate | Must be confirmed by CPA |
| Event 2 tax treatment | 30% effective rate | Must be confirmed by CPA |
| Tax-deferred distribution tax rate | 25% effective rate | Must be confirmed by CPA; state field may refine |
| Additional property income/expenses | Zero | Needed if it is an investment property |
| Real-estate appreciation | 2.5% placeholder | Needed for estate projections |
| Portfolio fees and tax drag | Zero | Needed for net-return accuracy |
| Legacy floor | $0 | Needed to distinguish consumption from preservation goals |
| Healthcare/long-term care shocks | Excluded | Needed for advanced risk modeling |
| 529 balances and contributions | Outside MVP baseline | Needed for complete family plan |

# 23. Developer Handoff Instructions

Treat Section 4 as the seed-data specification.

Implement calculation logic before visual design.

Do not hard-code client values inside formulas; store them as versioned assumptions.

Create automated tests from Section 19 before adding features.

Return an architecture diagram, entity-relationship diagram, and calculation-order document before coding the full UI.

Deliver the RRS normalization specification as a design document before phase 4b begins.

Any ambiguity must be represented as an explicit assumption, not guessed silently.

# 24. Approved Product Direction and Optimization Priority

FIOS is a personal financial decision engine that continuously identifies the optimal path to financial independence, quantifies every trade-off, and explains every recommendation.

Primary objective: minimize Work-Optional Age while maintaining the anchored-real spending level of Section 4.9 with an acceptable probability of lifetime success.

Legacy preservation is informational only and must not delay retirement unless the user explicitly enables a legacy constraint.

Balanced growth and income is the baseline investment philosophy.

Social Security is excluded from the baseline retirement requirement and treated as optional upside.

Every major financial decision must be evaluated against the same standardized metrics and compared with the active baseline scenario.

# 25. Primary Dashboard Metrics

| **Metric** | **Definition** | **Priority / Default** |
|---|---|---|
| Work-Optional Age (WOA) | Earliest age at which all enabled retirement tests pass. | Primary KPI |
| Financial Independence Date (FID) | Exact calendar date corresponding to the earliest passing retirement date. | Primary KPI |
| Retirement Readiness Score (RRS) | Configurable 0–100 composite score. | Primary KPI |
| Retirement Success Probability (RSP) | Monte Carlo probability that assets fund the plan through the selected terminal age. | Displayed against the Success Threshold (90% default) |
| Sustainable Annual Spending (SAS) | Maximum initial annual spending supported under the Success Threshold. | Core output |
| Freedom Margin (FM) | SAS minus desired annual spending. Positive means surplus capacity; negative means shortfall. | Core output |
| Liquidity Coverage Ratio (LCR) | Liquid investable assets divided by annual core expenses, expressed in years. | Risk / resilience |
| Concentration Risk Index (CRI) | Exposure to employer equity, individual securities, and illiquid real estate; equity component from the share ledger and price path. | Risk metric |
| Net Worth | Assets less liabilities. | Informational |
| Legacy Projection | Projected estate value by age. | Informational only |

## 25.1 Retirement Readiness Score

The initial default weighting is configurable and must be transparent:

| **Component** | **Default Weight** |
|---|---|
| Work-Optional Age progress | 35% |
| Retirement Success Probability | 30% |
| Freedom Margin | 20% |
| Liquidity Coverage | 10% |
| Concentration Risk | 5% |

The RSP component scores 100 at or above the Success Threshold and scales down below it per the normalization logic defined in the phase-4b design document.

The score must not conceal failed hard constraints. If the plan fails the longevity or essential-spending test, the dashboard must show that failure even if the composite score is high.

The application must show the component scores, weights, normalization logic, and assumption-confidence adjustment.

# 26. Recommendation and Optimization Engine

The system must answer: "What should I do next?" Recommendations must be generated from scenario comparisons, not generic financial advice.

| **Required field** | **Requirement** |
|---|---|
| Recommendation | Specific action, timing, amount, and funding source. |
| Reason | Plain-language explanation of why the action was generated. |
| Quantified impact | Before/after WOA, FID, RRS, RSP, FM, SAS, LCR, CRI, taxes, and estate value. |
| Trade-offs | Costs, risks, lost flexibility, and adverse outcomes. |
| Assumptions | Material assumptions and data confidence used. |
| Confidence | High, medium, or low, with a numerical confidence score where feasible. |
| Invalidation conditions | Changes that would make the recommendation inappropriate. |
| Supporting trace | Calculation references and affected model periods/accounts. |

Display the top five recommendations ranked by effect on financial independence, subject to hard risk constraints.

The optimization order is: earliest WOA/FID, required RSP, desired lifestyle, tax efficiency, liquidity resilience, and then informational estate value.

The engine must never recommend a materially earlier retirement if the configured Success Threshold or essential-spending floor is violated.

Recommendations must remain advisory; the application must not execute trades, transfers, tax filings, or legal documents.

## 26.1 Recommendation History

Store recommendation date, model version, scenario version, recommendation text, status, user response, expected impact, and realized impact where measurable.

Statuses: Active, Accepted, Completed, Dismissed, Superseded, and Expired.

Retain the original recommendation and assumptions even after the baseline changes.

# 27. Assumption Confidence and Explainability

| **Requirement** | **Specification** |
|---|---|
| Input confidence | Each material input stores source, verification date, confidence percentage, and status: Confirmed, Assumption, Placeholder, Estimated, or Derived. |
| Overall confidence | The system computes and displays an aggregate model-confidence indicator without replacing the underlying retirement metrics. |
| Explainability | Every output and recommendation must answer why, which assumptions drove it, what improved, what worsened, and what would change the conclusion. |
| No silent defaults | Any default must be visible, logged, and included in the report assumption register. |
| Reproducibility | A prior run must be reproducible using its immutable model version, scenario, assumptions, and random seed. |

# 28. Scenario Workspace and Versioned Assumptions

Scenarios are immutable children of a parent baseline until explicitly promoted.

Required named templates: retire now, retire at 57, retire at 58, retire at 59, purchase additional real estate, increase spending, market decline, reduced company payout, and higher payout tax. All retirement-timing templates use the anchored-real spending rule and retirement-linked liquidation.

Scenario comparison must show before/after values for all primary dashboard metrics.

Every assumption change requires an effective date, old value, new value, source, reason, user, and timestamp.

The system must generate a "What changed?" summary identifying the assumptions responsible for movement in WOA, FID, RRS, RSP, FM, and SAS.

# 29. Discovery Summary: Questions and Answers Driving the Project

This section preserves the discovery record that led to the FIOS requirements, updated where the v2.1 change requests superseded the original answers. It is intended to prevent the development team from repeating the baseline financial interview.

| **Discovery question** | **Confirmed answer / design implication** |
|---|---|
| What is the primary financial goal? | Retire early and stop working completely. |
| What is the current age and target retirement age? | Current age 53; planned retirement age 59, corresponding to 2032 under the current baseline. |
| What is current compensation? | $312,000 salary plus a $100,000 annual bonus. |
| How should salary change before retirement? | Increase salary by 2% annually; bonus remains static. |
| What is the current 401(k) balance and contribution policy? | $575,000 balance; contribute the maximum permitted annually including applicable catch-ups; use a 6% expected return. |
| What liquid investments exist outside retirement accounts? | $400,000 taxable brokerage account and $100,000 cash. |
| Are additional taxable contributions planned? | No additional taxable contributions are currently planned, although they remain an available option if needed. |
| What company equity is currently owned? | 166.122 shares at $21,589.92 per share, a derived value of $3,586,560.69 (supersedes the earlier $3.5 million estimate; CR-001). |
| What company-equity liquidity events are expected? | Sale of 111.163 shares in September 2026 at the prevailing price; sale of all remaining shares linked to the retirement date at the prevailing price anchor (CR-001, CR-005). The 2030 anchor of $70,000 per share reflects the user's price estimate; annual anchors for 2027–2029 are pending. |
| How should Event 1 be allocated? | Use a 30% tax placeholder; allocate $500,000 to additional real estate; invest the remaining net amount at 6%. |
| How should Event 2 be treated? | Retirement-linked: the candidate retirement date triggers full liquidation at the prevailing anchor price. Use a 30% tax placeholder until a tax estimate is confirmed. |
| What real estate is owned? | Primary residence valued at $700,000 with a $100,000 mortgage to be retired before retirement; lake home valued at $1.5 million with no mortgage. |
| How should the lake home be treated? | Strategic/emergency liquidity only; do not include its sale in the baseline retirement income plan. |
| What annual retirement spending is desired? | A real level anchored at $300,000 in 2032 dollars, converted per Section 4.9 for other retirement dates (CR-003). |
| How is the spending target composed? | $150,000 core living expenses; $40,000 travel; $20,000 vehicles; $20,000 hobbies; $30,000 home improvements; $40,000 miscellaneous; excludes mortgage debt service. |
| How is pre-retirement spending modeled? | Consumption residual: income less taxes, contributions, and debt service; displayed as a derived plausibility metric (CR-002). |
| What investment philosophy should the system use? | Balanced growth and income. |
| Should Social Security be required? | No. Exclude it from the baseline requirement and treat it as upside. |
| What is the priority between legacy and early retirement? | Prioritize retiring as early as possible. Legacy is secondary and informational. |
| Should retirement be able to precede full equity liquidation? | The sale date was a readiness estimate, not a constraint. Liquidation is linked to the retirement date so the solver can evaluate earlier retirement, pricing the sale at that date's anchor (CR-005). |
| What single question should the system answer? | If I stop working today, can I maintain my desired lifestyle for the rest of my life while preserving required financial resilience? If not, what is the earliest date I can do so? |
| Why was a dedicated software project required? | The plan depends on multiple account types, private-company liquidity events, taxes, real estate, retirement timing, spending flexibility, market uncertainty, and decision comparisons. A static calculator or isolated spreadsheet cannot adequately maintain version history, explain recommendations, run simulations, and compare decisions over time. |

# 30. Requirements Freeze and Change Control

Version 2.1 is the approved frozen baseline for architecture, data-model design, calculation-engine implementation, and estimation. It supersedes Version 2.0 through change requests CR-001 through CR-007 and clarification log entries CL-1 through CL-6, recorded in Appendix C.

No new feature or metric may enter the active build without a written change request containing rationale, priority, affected requirements, data-model impact, calculation impact, security impact, testing impact, cost, and schedule effect.

Clarifications that do not change system behavior may be recorded without a version increment. Behavioral changes require a minor or major version increment.

The development team must return an architecture diagram, entity-relationship diagram, calculation specification, threat model, and delivery plan before full application implementation.

# Appendix A — Baseline Snapshot

| **Category** | **Amount** |
|---|---|
| Cash | $100,000.00 |
| 401(k) | $575,000.00 |
| Taxable brokerage | $400,000.00 |
| Company equity (166.122 shares at $21,589.92) | $3,586,560.69 |
| Primary residence | $700,000.00 |
| Lake home | $1,500,000.00 |
| Total assets | $6,861,560.69 |
| Primary mortgage | ($100,000.00) |
| Net worth | $6,761,560.69 |
| Event 1 gross (111.163 shares at $21,589.92) | $2,400,000.28 |
| Event 1 estimated tax at 30% | ($720,000.08) |
| Event 1 property allocation | ($500,000.00) |
| Event 1 invested proceeds | $1,180,000.20 |
| Shares remaining after Event 1 | 54.959 |
| Event 2 gross at $70,000 anchor (baseline) | $3,847,130.00 |
| Event 2 estimated tax at 30% | ($1,154,139.00) |
| Event 2 invested proceeds | $2,692,991.00 |
| Retirement spending anchor (2032 dollars) | $300,000.00 |

# Appendix B — Company-Equity Ledger Rule

Company equity is share-denominated. Value is always derived as shares held multiplied by the prevailing price-path anchor. A liquidity event reduces shares held by the shares sold; gross proceeds are derived, never entered. Gain is share-price appreciation and requires no separate reconciliation. The reconciliation warning of Version 2.0 is retired. If a user attempts to enter a standalone dollar valuation for company equity, the application must reject the entry and direct the user to the share ledger and price path.

# Appendix C — Change Record: Version 2.0 to Version 2.1

## CR-001: Share-denominated company-equity ledger and price path

Rationale: Source data is share-denominated (166.122 shares at $21,589.92). The v2.0 dollar figures were derived approximations that did not reconcile: the $3.5M carrying value understated the derived value by approximately $87K, and the stated $2.1M Event 1 gross implied an unexplained 12.5% discount to the prevailing price. The extinguishment problem identified in review disappears when shares are the unit of account. Changes: share ledger and PricePath entities; both events specified in shares; gross proceeds derived; net worth acceptance criterion restated to $6,761,560.69; Event 1 values restated ($2,400,000.28 gross, $720,000.08 tax, $1,680,000.20 net, $1,180,000.20 invested); Appendix B replaced; lower-payout scenario reparameterized as a lower price anchor. Affected: Sections 3.1, 4.3, 4.4, 4.7, 7.4, 8.1, 10, 11, 19, 22, 29, Appendices A and B.

## CR-002: Pre-retirement cash flow rule and mortgage payoff boundary

Rationale: v2.0 specified accumulation-phase income but no expense line, making cash conservation undefined. Changes: consumption-residual rule (Section 4.10); Implied Pre-Retirement Spending displayed as a derived metric; residual applies to salary and bonus only, never to liquidity-event proceeds; primary mortgage fully retired before retirement with a payoff-by-December-2031 placeholder; $300K target confirmed to exclude mortgage debt service; conservation identity added to acceptance criteria. Affected: Sections 4.4, 4.9, 4.10, 7.2, 12, 13, 19, 20, 22.

## CR-003: Spending target defined as anchored real level

Rationale: The WOA solver evaluates candidate dates other than 2032, but v2.0 defined the target only for a 2032 retirement. Changes: target is a real level anchored at $300,000 in 2032 dollars, converted by (1 + i)^(Y − 2032) for candidate year Y; categories scale proportionally; retirement-timing scenarios use the rule; acceptance values $300,000 (2032), $291,262 (2031), $309,000 (2033). Affected: Sections 4.9, 5, 6, 8.1, 19, 24, 28, 29.

## CR-004: Single success threshold

Rationale: Sections 6.2 (90%) and 25 (95%) specified conflicting probability values for overlapping roles. A single 90% threshold was selected: half the spending target is flexible discretionary spending already defended by guardrails, so gating at 95% purchases insurance against scenarios with a cheaper existing defense at the cost of roughly an additional working year. Changes: one configurable Success Threshold (90% default) gates the WOA stress test, appears on the dashboard, and anchors the RRS probability component; the 95% target row deleted; the lower-payout scenario designated the stress vehicle for share-price risk, since the Monte Carlo price path is deterministic in the MVP. Affected: Sections 6.2, 9, 25, 25.1, 26.

## CR-005: Retirement-linked liquidation and annual price anchors

Rationale: The 2030 sale date was a readiness estimate, not a constraint. Fixing it blocked evaluation of earlier retirement and concealed the price-appreciation cost of retiring sooner. Changes: Event 2 date defaults to the scenario retirement date, selling all remaining shares at the prevailing anchor; date_mode field (fixed or retirement-linked); annual anchor table 2026–2030 with step interpolation and flat extension; solver prices each candidate date's liquidation from the anchor table; concentration test satisfied by construction in the baseline; market-decline scenario extended to shock the equity price path; acceptance test that a 2028 candidate prices at the 2028 anchor. Affected: Sections 4.7, 4.7.1, 6.1, 8.1, 11, 19, 28, 29.

## CR-006: Integration of Sections 24–28 into modules and delivery plan

Rationale: FID, Freedom Margin, RRS, and the recommendation engine appeared in acceptance criteria and dashboard requirements but had no phase assignment or module ownership. Changes: Recommendations and Scoring module rows added; FID and FM assigned to phase 2; new phase 4b (Readiness Score) with the hard-constraint override exit criterion; recommendation engine split into phases 6a (generation and ranking) and 6b (history and realized-impact tracking); Legacy and Reporting renumbered to phase 7, Integrations to phase 8; Section 13 cards annotated with phase availability; RRS normalization specification added as a pre-4b design deliverable. Affected: Sections 10, 13, 19, 21, 23, 25.1, 26.

## CR-007: WOA solver strategy

Rationale: A linear monthly scan with full model runs per candidate is computationally infeasible once Monte Carlo gating is enabled. Changes: monotonicity asserted as a tested model invariant; coarse annual deterministic scan, monthly bisection, Monte Carlo verification at the candidate solution only, forward stepping on verification failure; variance-consistent seeds during stepping; Not Achievable outcome bounds the search; performance targets of 2 seconds deterministic and 45 seconds with verification. Affected: Sections 5, 6, 6.3, 20.

## Clarification Log

CL-1: Liquidity events carry an occurred flag; at settlement, actual gross, tax withheld, and net proceeds replace derived values and are reclassified Confirmed. The exact September 2026 sale date is pending; 2026-09-30 stands as placeholder.

CL-2: Tax-deferred retirement distributions use a 25% effective-rate placeholder, unresolved pending CPA confirmation. Rationale: blended mid-bracket estimate at the target spending level; plan sensitivity is low because the 401(k) is roughly a tenth of projected retirement assets; the Household state field may refine the placeholder before CPA confirmation.

CL-3: The 401(k) statutory limit table must seed the age-50 catch-up and the age 60–63 enhanced catch-up, both applicable within the projection window.

CL-4: Price anchors for 2027, 2028, and 2029 are pending from the user and slot into the Section 4.7.1 table when supplied.

CL-5: Real-estate appreciation (2.5% placeholder) and zero income/expenses on the planned additional property are unchanged and remain open items.

CL-6: The implementation-estimate deliverable is removed from Sections 23 and 30. Development is performed with Claude Code, where an effort estimate serves no scheduling or budgeting function. The remaining pre-implementation deliverables (architecture diagram, ERD, calculation specification, threat model, delivery plan) are unchanged.

FIOS PRD v2.1 — Requirements Frozen — July 2026
