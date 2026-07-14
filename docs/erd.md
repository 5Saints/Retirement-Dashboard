# FIOS Entity-Relationship Diagram

Covers every entity from PRD Section 11. Phase 1 implements these as in-memory Python objects
(`fios_engine/models.py`); the relational schema below is the target for the future persistence
layer (Phase 3+).

```mermaid
erDiagram
    HOUSEHOLD ||--o{ PERSON : has
    HOUSEHOLD ||--o{ EQUITY_POSITION : owns
    HOUSEHOLD ||--o{ REAL_ESTATE : owns
    HOUSEHOLD ||--o{ SCENARIO : plans

    PERSON ||--o{ ACCOUNT : owns
    PERSON ||--o{ INCOME_STREAM : earns

    ACCOUNT ||--o{ ASSET : holds

    EQUITY_POSITION ||--o{ PRICE_PATH : "priced by"
    EQUITY_POSITION ||--o{ LIQUIDITY_EVENT : "liquidated via"

    LIABILITY }o--|| ASSET : "may be linked to"

    SCENARIO ||--o{ SCENARIO_OVERRIDE : overrides
    SCENARIO ||--o{ PROJECTION_RESULT : produces
    SCENARIO ||--o{ SIMULATION_RUN : produces
    SCENARIO ||--o{ DECISION : evaluates
    SCENARIO ||--o{ RECOMMENDATION : generates
    SCENARIO ||--o| SCENARIO : "parent of"

    SCENARIO_OVERRIDE }o--|| ASSUMPTION : overrides

    RECOMMENDATION ||--o{ RECOMMENDATION_HISTORY : tracks

    ASSUMPTION ||--o{ AUDIT_EVENT : "changes logged as"

    HOUSEHOLD {
        uuid id PK
        string name
        string state
        string filing_status
        string base_currency
    }
    PERSON {
        uuid id PK
        uuid household_id FK
        date birth_date
        string role
        date retirement_date
        int life_expectancy
    }
    ACCOUNT {
        uuid id PK
        uuid owner_id FK
        string type
        string tax_treatment
        string institution
        decimal balance
        date valuation_date
        string liquidity_class
    }
    ASSET {
        uuid id PK
        uuid account_id FK
        string asset_class
        string ticker_or_description
        decimal value
        decimal basis
        bool employer_related
    }
    EQUITY_POSITION {
        uuid id PK
        uuid household_id FK
        string description
        decimal share_quantity
        decimal basis
        bool employer_related
    }
    PRICE_PATH {
        uuid id PK
        uuid equity_position_id FK
        date effective_date
        decimal price
        string interpolation_mode
        string status
        string confidence
    }
    LIABILITY {
        uuid id PK
        string type
        decimal balance
        decimal rate
        decimal payment
        date maturity
        uuid linked_asset_id FK
        string payoff_boundary_rule
    }
    INCOME_STREAM {
        uuid id PK
        uuid person_id FK
        string type
        decimal amount
        string frequency
        date start_date
        date end_date
        decimal growth_rate
    }
    EXPENSE {
        uuid id PK
        string category
        bool essential_flag
        decimal anchor_amount
        int anchor_year
        string frequency
        decimal inflation_rate
        date start_date
        date end_date
    }
    LIQUIDITY_EVENT {
        uuid id PK
        uuid equity_position_id FK
        string date_mode
        date date
        decimal shares_sold
        string tax_rule
        decimal net_allocation
        bool occurred_flag
    }
    REAL_ESTATE {
        uuid id PK
        decimal value
        decimal debt
        decimal income
        decimal expenses
        decimal appreciation
        string liquidity_role
    }
    ASSUMPTION {
        uuid id PK
        string key
        decimal value
        string unit
        string status
        date effective_date
        string source
        string confidence
    }
    SCENARIO {
        uuid id PK
        uuid parent_id FK
        string name
        datetime created_at
        datetime locked_at
    }
    SCENARIO_OVERRIDE {
        uuid scenario_id FK
        uuid assumption_id FK
        decimal overridden_value
    }
    PROJECTION_RESULT {
        uuid scenario_id FK
        string period
        string metric_name
        decimal value
    }
    SIMULATION_RUN {
        uuid scenario_id FK
        int seed
        int iterations
        string model_version
        datetime timestamp
    }
    DECISION {
        uuid id PK
        uuid scenario_id FK
        string type
        date date
        decimal amount
        string funding_source
        string recurring_effect
    }
    RECOMMENDATION {
        uuid id PK
        uuid scenario_id FK
        datetime created_at
        string model_version
        string scenario_version
        string text
        string action
        date timing
        decimal amount
        string funding_source
        string expected_impact
        string confidence
        string invalidation_conditions
        string status
    }
    RECOMMENDATION_HISTORY {
        uuid recommendation_id FK
        string status_change
        string user_response
        string realized_impact
        datetime timestamp
    }
    AUDIT_EVENT {
        uuid id PK
        string entity
        string field
        string old_value
        string new_value
        string user
        datetime timestamp
        string reason
    }
```

## Notes

- `EQUITY_POSITION` is the sole source of truth for company-equity value: value is always
  `share_quantity × PRICE_PATH.price` at a given date. No `value` column exists on
  `EQUITY_POSITION` itself (PRD Appendix B / CR-001) — this is enforced in Phase 1 by the Python
  model simply not exposing a settable dollar-value field.
- `LIQUIDITY_EVENT.date_mode` is `fixed` or `retirement_linked`; a `retirement_linked` event's
  effective date resolves to the scenario's candidate retirement date at evaluation time
  (CR-005), so it has no fixed `date` until it either occurs or is overridden.
- `ASSUMPTION.status` takes the four values from Section 4/27: `confirmed`, `assumption`,
  `placeholder`, `derived` (Phase 1 also allows `estimated` per Section 27's five-way status).
- Phase 1 does not implement `SCENARIO_OVERRIDE`, `PROJECTION_RESULT` persistence,
  `SIMULATION_RUN`, `DECISION`, `RECOMMENDATION`, `RECOMMENDATION_HISTORY`, or `AUDIT_EVENT` — the
  in-memory engine returns a result object instead of writing rows. These entities are shown here
  because they're required for the target Phase 3+ persistence layer.
