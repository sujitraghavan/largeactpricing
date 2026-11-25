# Commercial Auto Loss Rating — Online Rating Model Specification

**Project:** Large Account Pricing — Commercial Auto Loss Rating Engine
**Date:** 2026-11-25
**Status:** Draft for review
**Stack:** Python / FastAPI / Supabase (PostgreSQL)

---

## 1. Intent & Why

Underwriters currently rate large commercial auto accounts using an Excel workbook (`Commercial_Auto_Loss_Rating.xlsx`). That workflow suffers from:

- **Data incompleteness** — required cells left blank, no validation
- **Data inconsistency** — same account rated differently by different underwriters
- **Model drift** — updates to rating factors (LDFs, trends, state rules) not propagated to all copies
- **No audit trail** — no record of what inputs produced a given quote

**Goal:** Replace the workbook with a web application where underwriters enter/import account data, the engine runs the full actuarial calculation deterministically, and the resulting quote is stored in Supabase with clean, versioned data.

---

## 2. Goals, Non-Goals, Anti-Goals

### Goals
- **Rating accuracy** — reproduce the Excel calculation chain exactly (LDF by maturity, trend, credibility, schedule mod bounds, LER tables, state LCM/tax/surcharge)
- **Data integrity** — validated inputs, required fields enforced, referential integrity to model parameter tables
- **50-state coverage** — simulated but realistic state rating factors in a lookup table
- **Quote persistence** — every rated quote stored in Supabase with full breakdown
- **Loss run flexibility** — manual entry **and** CSV/Excel upload with template generation
- **Structure comparison** — instant side-by-side premium for Deductible vs SIR at multiple retentions

### Non-Goals (v1)
- User authentication / RBAC
- Model versioning / change management
- Audit logging
- Approval workflows
- Multi-user collaboration

### Anti-Goals
- Recreating Excel as a web grid — this is a structured form + calculation engine, not a spreadsheet clone
- Hardcoding state factors in code — they live in DB tables

---

## 3. High-Level Architecture

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Browser    │────▶│  FastAPI App     │────▶│  Supabase       │
│  (React/    │     │  /rating-engine  │     │  (PostgreSQL)   │
│   HTMX)     │     │                  │     │                 │
└─────────────┘     └──────────────────┘     └─────────────────┘
                           │                        ▲
                           ▼                        │
                    ┌──────────────────┐            │
                    │  Rating Engine   │            │
                    │  (pure Python)   │            │
                    └──────────────────┘            │
                           │                        │
                           ▼                        │
                    ┌──────────────────┐            │
                    │  Model Params    │────────────┘
                    │  (LDF, LER,      │
                    │   Trends,        │
                    │   State Rules)   │
                    └──────────────────┘
```

- **FastAPI** serves the UI (HTMX templates or static React) and exposes `/api/v1/rate` endpoint
- **Rating engine** is a pure-Python module with zero framework dependencies — testable in isolation
- **Supabase** stores: account inputs, loss runs, quotes, and model parameter tables
- **Model parameters** are seeded via migration scripts (50-state simulation + LDF/LER/trend tables)

---

## 4. Data Model — User Inputs vs Model Parameters

### 4.1 User Inputs (per-quote, submitted by underwriter)

| Table | Key Fields | Notes |
|-------|-----------|-------|
| `accounts` | `id`, `named_insured`, `primary_state`, `effective_date`, `expiration_date`, `valuation_date`, `csl`, `experience_cap`, `structure` (deductible/SIR), `retention`, `schedule_mod`, `full_credibility_claim_count`, `fixed_expense_per_unit`, `expiring_premium_per_unit`, `created_at`, `created_by` | One row per quote |
| `fleet_exposures` | `id`, `account_id`, `state`, `vehicle_class`, `operating_radius`, `units_2022`, `units_2023`, `units_2024`, `units_2025`, `projected_units`, `projected_trailers` | Composite unique on (account_id, state, vehicle_class, operating_radius) |
| `loss_occurrences` | `id`, `account_id`, `occurrence_id`, `loss_date`, `paid_indemnity`, `case_indemnity`, `paid_alae`, `case_alae`, `total_incurred`, `at_policy_limit`, `capped_loss`, `above_cap`, `policy_year` | One row per occurrence; `capped_loss` = min(total_incurred, experience_cap); `above_cap` = max(0, total_incurred - experience_cap) |

### 4.2 Model Parameters (actuary-maintained, seeded at deploy)

| Table | Key Fields | Source |
|-------|-----------|--------|
| `ldf_factors` | `age_floor_months`, `limited_ldf` | Tab 04, rows 5–11 |
| `retention_factors` | `retention`, `deductible_ler`, `sir_ler`, `ded_fee_per_unit`, `sir_fee_per_unit` | Tab 04, rows 5–9 |
| `trend_factors` | `frequency_trend`, `severity_trend`, `combined_trend` | Tab 04, rows 13–15 (single-row table) |
| `state_rating_rules` | `state_code`, `manual_capped_per_unit`, `excess_capped_ratio`, `variable_expense`, `profit_provision`, `lcm_override`, `applied_lcm`, `min_mod`, `max_mod`, `lcr_confirmed`, `waiver_allowed`, `customer_tax_rate`, `surcharge_rate`, `flat_charge` | **50 states** — simulated from OH/PA/IN pattern |

---

## 5. State Rating Rules — 50-State Simulation Strategy

The Excel only has OH, PA, IN. We need realistic values for all 50 states.

### Seeding Approach
1. **Base distributions** derived from the three known states:
   - Manual capped/unit: ~$1,900–$2,350 (log-normal, μ=7.7, σ=0.15)
   - Excess/capped ratio: 0.41–0.48 (beta, α=20, β=25)
   - Variable expense: 0.18–0.21 (beta, α=40, β=160)
   - Profit provision: 0.05–0.055 (tight normal)
   - LCM override: mostly NULL (80%), else 1.30–1.40
   - Min mod: -0.15 to -0.05
   - Max mod: 0.10–0.15
   - Tax: 0.009–0.017
   - Surcharge: 0.002–0.003
   - Flat charge: $15–$35

2. **Regional adjustments** — apply multipliers by census region:
   - Northeast: manual ×1.05, tax ×1.15
   - Midwest: base (OH/IN reference)
   - South: manual ×0.95, tax ×0.9
   - West: manual ×1.10, tax ×1.2

3. **Seed script** (`scripts/seed_state_rules.py`) generates deterministic values (seeded RNG) so re-runs are idempotent.

4. **Actuary review** — the seeded table is a starting point; actuaries can override any state via direct DB update or admin UI (v2).

---

## 6. Rating Engine — Calculation Specification

The engine is a pure function: `rate(account, fleet_exposures, loss_occurrences, params) → QuoteResult`

### 6.1 Experience Rating (Tab 05)

For each policy year (2022–2025):

1. **Unit years** = sum of projected units across all fleet exposure rows for that year
2. **Occurrences** = count of loss_occurrences for that policy_year
3. **Capped incurred** = sum(capped_loss) for that policy_year
4. **Age (months)** = months from valuation_date to midpoint of policy year (or use fixed: 48, 36, 24, 12)
5. **Limited LDF** = lookup in `ldf_factors` where `age_floor_months` ≤ age, take max age_floor
6. **Ultimate capped** = capped_incurred × limited_ldf
7. **Trend years** = (effective_date - policy_year_midpoint) / 365.25
8. **Trended ultimate** = ultimate_capped × (1 + combined_trend) ^ trend_years
9. **Burn cost / unit** = trended_ultimate / unit_years

**Pooled burn cost** = weighted average of 4 years' burn cost/unit, weights = unit_years

**Credibility** = min(1, sqrt(total_occurrences / full_credibility_claim_count))
- Uses classical frequency-based credibility: `Z = min(1, sqrt(N / K))` where N = total occurrences, K = full credibility standard (1084)

### 6.2 State Pricing (Tab 05 → 06)

For each state with projected_units > 0:

1. **Manual capped** = `state_rating_rules.manual_capped_per_unit`
2. **Blended capped** = credibility × pooled_burn_cost + (1 - credibility) × manual_capped
3. **Excess/unit** = blended_capped × state_rating_rules.excess_capped_ratio
4. **Ground-up/unit** = blended_capped + excess/unit
5. **Schedule mod** = account.schedule_mod, clamped to [min_mod, max_mod] for that state
   - If `lcr_confirmed` AND `waiver_allowed` both true → no clamping
   - Else clamp and flag "Bound applied" if modified
6. **Applied LCM** = state_rating_rules.applied_lcm (or computed: (1 + var_exp + profit) / (1 - var_exp - profit))
7. **Selected premium (state)** = ground-up/unit × projected_units × (1 + schedule_mod) × applied_lcm
8. **Tax** = selected_premium × customer_tax_rate
9. **Surcharge** = selected_premium × surcharge_rate
10. **Flat charge** = flat_charge (once per active state)
11. **Total payable (state)** = selected_premium + tax + surcharge + flat_charge

### 6.3 Structure Comparison (Tab 06)

For each structure (Deductible, SIR) and retention level (0, 10000, 25000, 50000, 100000):

1. **LER** = retention_factors.[deductible_ler | sir_ler] for that retention
2. **Fee/unit** = retention_factors.[ded_fee_per_unit | sir_fee_per_unit]
3. **Loss eliminated** = ground-up_total × LER
4. **Technical premium** = sum over states of (state_selected_premium × (1 - LER)) + fee/unit × total_projected_units
5. **Total payable** = technical_premium + sum(state_tax + surcharge + flat_charge)
6. **Credit vs $0** = technical_premium_at_zero - technical_premium_at_retention
7. **Credit %** = credit / technical_premium_at_zero

**Selected structure/retention** comes from account record; quote summary shows that row highlighted.

---

## 7. API Specification

### POST `/api/v1/rate`
**Request:**
```json
{
  "account": { ... },           // AccountInput model
  "fleet_exposures": [ ... ],   // FleetExposureInput[]
  "loss_occurrences": [ ... ],  // LossOccurrenceInput[] (optional if upload used)
  "loss_run_file_id": "uuid"    // Optional: reference to uploaded file
}
```

**Response:**
```json
{
  "quote_id": "uuid",
  "account": { ... },
  "experience_rating": {
    "by_year": [ { "policy_year", "unit_years", "occurrences", "capped_incurred", "age_months", "ldf", "ultimate_capped", "trend_years", "trended_ultimate", "burn_cost_per_unit" }, ... ],
    "pooled_burn_cost": 6047.65,
    "credibility": 0.2313
  },
  "state_pricing": [ { "state", "projected_units", "manual_capped", "blended_capped", "excess_per_unit", "ground_up_per_unit", "schedule_mod", "schedule_check", "applied_lcm", "tax_rate", "surcharge_rate", "flat_charge", "selected_premium", "tax_charges", "total_payable" }, ... ],
  "structure_comparison": [ { "structure", "retention", "ler", "technical_premium", "credit_vs_zero", "credit_pct", "total_payable" }, ... ],
  "summary": {
    "selected_structure": "Deductible",
    "selected_retention": 25000,
    "technical_premium": 590661.10,
    "tax_and_charges": 9205.08,
    "total_payable": 599866.18,
    "premium_per_unit": 4311.39,
    "rate_change_vs_expiring": 0.1346
  },
  "created_at": "2026-11-25T..."
}
```

### POST `/api/v1/loss-run/upload`
- Accepts `multipart/form-data` with CSV or Excel file
- Validates columns against template
- Returns `file_id` + parsed preview (first 10 rows) for confirmation

### GET `/api/v1/loss-run/template`
- Returns `Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
- Excel file with headers: `Occurrence ID, Loss Date, Valuation Date, Paid Indemnity, Case Indemnity, Paid ALAE, Case ALAE`
- Includes 3 example rows

### GET `/api/v1/model-parameters/state-rules`
- Returns all 50 states' rating rules (for UI reference table)

### GET `/api/v1/quotes/{quote_id}`
- Retrieve stored quote with full breakdown

---

## 8. Quote Storage Schema (Supabase)

```sql
-- Core quote record
CREATE TABLE quotes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID REFERENCES accounts(id),
    experience_rating JSONB NOT NULL,      -- Full experience_rating object
    state_pricing JSONB NOT NULL,          -- Full state_pricing array
    structure_comparison JSONB NOT NULL,   -- Full structure_comparison array
    summary JSONB NOT NULL,                -- Summary object
    selected_structure TEXT NOT NULL,
    selected_retention INTEGER NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    created_by TEXT
);

-- Index for reporting
CREATE INDEX idx_quotes_account ON quotes(account_id);
CREATE INDEX idx_quotes_created ON quotes(created_at);
```

**Rationale:** Store the full calculation output as JSONB — preserves exact numbers for audit/reporting, avoids schema churn when model evolves. Structured columns on the summary fields enable fast dashboards.

---

## 9. Loss Run Import — CSV/Excel Template

**Required columns (exact names):**
| Column | Type | Required | Notes |
|--------|------|----------|-------|
| Occurrence ID | string | Yes | Unique per account |
| Loss Date | date (YYYY-MM-DD) | Yes | |
| Valuation Date | date (YYYY-MM-DD) | Yes | Typically same for all rows |
| Paid Indemnity | number | Yes | ≥ 0 |
| Case Indemnity | number | Yes | ≥ 0 |
| Paid ALAE | number | Yes | ≥ 0 |
| Case ALAE | number | Yes | ≥ 0 |

**Derived (computed on import):**
- `Total Incurred` = Paid Indemnity + Case Indemnity + Paid ALAE + Case ALAE
- `At Policy Limit` = min(Total Incurred, CSL) — CSL from account
- `Capped Loss` = min(Total Incurred, Experience Cap)
- `Above Cap` = max(0, Total Incurred - Experience Cap)
- `Policy Year` = YEAR(Loss Date)

**Validation rules:**
- All amounts ≥ 0
- Loss Date ≤ Valuation Date
- Valuation Date = account.valuation_date (warn if mismatch)
- No duplicate Occurrence IDs within account
- Policy Year must fall within 4-year experience window

---

## 10. UI Workflow (Single-Page Application)

```
┌─────────────────────────────────────────────────────────────┐
│  Commercial Auto Loss Rating                                │
├─────────────────────────────────────────────────────────────┤
│  Step 1: Account Terms                    [Next →]          │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Named Insured: [Buckeye Regional Freight      ▼]    │   │
│  │ Primary State: [OH                          ▼]    │   │
│  │ Effective Date: [2026-01-01]  Expiration: [2027-01-01]│
│  │ Valuation Date: [2026-01-01]                       │   │
│  │ CSL: [$1,000,000]  Experience Cap: [$100,000]      │   │
│  │ Structure: [Deductible ▼]  Retention: [$25,000 ▼]   │   │
│  │ Schedule Mod: [-8%]  Credibility Std: [1084]       │   │
│  │ Fixed Exp/Unit: [$85]  Expiring Prem/Unit: [$3,800] │   │
│  └─────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│  Step 2: Fleet Exposures                    [Next →]          │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ [+ Add Row]  State │ Vehicle Class │ Radius │ 2022│...│   │
│  │                    OH │ Heavy Truck  │ Local  │  22 │...│   │
│  │                    OH │ Tractor      │ Regional│ 29 │...│   │
│  │                    PA │ Heavy Truck  │ Local  │  13 │...│   │
│  │                    ...                                              │   │
│  │                    [Import CSV]  [Export Template]               │   │
│  └─────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│  Step 3: Loss Run                           [Next →]          │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ [Upload CSV/Excel]  [Download Template]             │   │
│  │                                                    │   │
│  │  Occurrence ID │ Loss Date  │ Paid Ind │ Case Ind │...│   │
│  │  OCC-1001      │ 2022-01-03 │ 37,467   │  2,391   │...│   │
│  │  OCC-1002      │ 2022-02-04 │  2,969   │    190   │...│   │
│  │  ...                                                    │   │
│  │  [+ Add Manual Row]                                   │   │
│  └─────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│  Step 4: Review & Rate                      [Rate Quote]    │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ ▸ Experience Rating    ▸ State Pricing              │   │
│  │ ▸ Structure Comparison ▸ Summary                    │   │
│  │                                                     │   │
│  │  [Recalculate]  [Save Quote]  [Export PDF]          │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

- **HTMX-driven** — partial updates, no heavy SPA framework needed
- **Validation inline** — red borders + toast on invalid fields
- **Rate Quote** → POST `/api/v1/rate` → renders results in Step 4 tabs
- **Save Quote** → POST `/api/v1/quotes` (idempotent by quote_id) → success toast

---

## 11. Project Structure

```
largeactpricing/
├── app/
│   ├── main.py                 # FastAPI app, routes
│   ├── models/
│   │   ├── inputs.py           # Pydantic models for API request/response
│   │   ├── database.py         # SQLAlchemy models for Supabase tables
│   │   └── parameters.py       # Model parameter table models
│   ├── services/
│   │   ├── rating_engine.py    # Pure calculation logic (no DB deps)
│   │   ├── loss_run_parser.py  # CSV/Excel → LossOccurrenceInput[]
│   │   └── quote_store.py      # Supabase CRUD
│   ├── api/
│   │   ├── rate.py             # POST /rate
│   │   ├── loss_run.py         # Upload, template
│   │   └── quotes.py           # GET /quotes/{id}
│   ├── templates/              # Jinja2/HTMX templates
│   └── static/                 # CSS, JS
├── scripts/
│   ├── seed_state_rules.py     # 50-state simulation
│   ├── seed_ldf_ler.py         # LDF, retention, trend tables
│   └── migrate.py              # Alembic wrapper
├── tests/
│   ├── test_rating_engine.py   # Golden master vs Excel outputs
│   ├── test_loss_run_parser.py
│   └── test_api.py
├── alembic/                    # Migrations
├── requirements.txt
├── pyproject.toml
└── SPEC.md
```

---

## 12. Testing Strategy

### Golden Master Tests
- **Fixture:** Export the Excel's Tab 05 & 06 outputs as JSON
- **Test:** Run `rating_engine.rate()` with the exact same inputs → assert numeric equality (tolerance 1e-6)
- Covers: experience rating, state pricing, structure comparison

### Property-Based Tests
- Credibility ∈ [0, 1]
- Schedule mod clamped to [min_mod, max_mod] unless LCR+waiver
- Total payable = technical_premium + tax + surcharge + flat_charge
- Credit % ≥ 0, increases with retention

### Integration Tests
- Upload loss run CSV → parse → rate → store → retrieve

---

## 13. Deployment & Operations

| Item | Decision |
|------|----------|
| Hosting | Fly.io / Render / Railway (Docker) |
| Database | Supabase (managed PostgreSQL) |
| Migrations | Alembic, run at deploy |
| Seeding | `scripts/seed_*.py` run once post-migration |
| Config | Environment variables (Supabase URL/key, app secret) |
| Observability | Structured logs (JSON), basic health endpoint |

---

## 14. Open Questions for Review

1. **Schedule mod bounds** — The Excel shows "Bound applied" for PA (mod -0.05 vs min -0.05). Is the clamp inclusive? (Spec assumes yes)
2. **Trend years calculation** — Excel uses fractional years (e.g., 3.000684...). Confirm: `(effective_date - policy_year_midpoint).days / 365.25`?
3. **Applied LCM formula** — Excel shows `Applied LCM` column with values like 1.3245. Is this `(1 + var_exp + profit) / (1 - var_exp - profit)` or a separate override? (Spec uses override when present, else computed)
4. **Zero-dollar claims** — Tab 03 says "including zero-dollar claims." Should upload template include a zero-row example?
5. **Trailer exposure** — Tab 02 has "Projected trailers" but it's not used in rating. Keep for reference only?

---

## 15. Next Steps

1. **Approve this spec** → I'll scaffold the FastAPI project with SQLAlchemy + Pydantic models
2. **Run seed scripts** → Populate 50-state rules, LDF, LER, trends in Supabase
3. **Implement rating_engine.py** with golden master tests against Excel outputs
4. **Build API endpoints** + HTMX templates
5. **Loss run upload + template generation**
6. **Quote storage + retrieval**
7. **End-to-end test** with the Buckeye Regional Freight data

---

*End of SPEC.md*