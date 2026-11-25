# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Commercial Auto Loss Rating Engine** — An online rating model for commercial auto liability insurance, ported from an Excel workbook (`Commercial_Auto_Loss_Rating.xlsx`). Underwriters enter account data → engine runs actuarial calculations → quote stored in Supabase.

**Stack:** Python / FastAPI / Supabase (PostgreSQL via SQLAlchemy + asyncpg) / HTMX frontend (planned)

---

## Common Commands

```bash
# Install deps
pip install -r requirements.txt

# Lint + format
ruff check . && ruff format .

# Type check
mypy app/

# Run all tests
pytest tests/

# Run single test
pytest tests/test_rating_engine.py::test_experience_rating_matches_excel -v

# Start dev server
uvicorn app.main:app --reload

# DB migrations
alembic upgrade head
alembic revision --autogenerate -m "description"

# Seed model parameters (requires Supabase creds)
python scripts/seed_ldf_ler.py
python scripts/seed_state_rules.py
```

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Browser (HTMX)                              │
└─────────────────────────────────┬───────────────────────────────────┘
                                  │ HTTP
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│  FastAPI App (app/main.py)                                          │
│  • POST /api/v1/rate      — Full rating calculation                │
│  • GET  /api/v1/loss-run/template  — Excel template download       │
│  • GET  /api/v1/quotes/{id}  — Retrieve stored quote               │
│  • GET  /health            — Health check                          │
└─────────────────────────────────┬───────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Rating Engine (app/services/rating_engine.py)                     │
│  Pure Python, zero framework deps. Testable in isolation.          │
│  Input: AccountParams + FleetExposureRow[] + LossOccurrenceRow[]   │
│  Output: QuoteResult (experience + state pricing + structures)     │
│  1. Experience rating: LDF by maturity → trend → pooled burn cost  │
│  2. Credibility: sqrt(total_occurrences / full_cred_claim_count)   │
│  3. State pricing: manual → blended → excess → schedule mod → LCM  │
│  4. Structure comparison: Deductible/SIR × 5 retentions            │
└─────────────────────────────────┬───────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Supabase (PostgreSQL)                                              │
│  Tables: accounts, fleet_exposures, loss_occurrences,              │
│  ldf_factors, retention_factors, trend_factors,                    │
│  state_rating_rules (50 states), quotes (JSONB)                    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Key Files

| File | Purpose |
|------|---------|
| `app/main.py` | FastAPI routes, in-memory 50-state params (placeholder until DB wiring) |
| `app/models.py` | Pydantic API models + SQLAlchemy ORM models |
| `app/services/rating_engine.py` | **Core actuarial logic** — pure dataclasses, no framework |
| `app/services/__init__.py` | Exports engine types + in-memory params (LDF_TABLE, STATE_RULES, etc.) |
| `app/config.py` | Settings via pydantic-settings (`.env` → Supabase URLs) |
| `tests/test_rating_engine.py` | 6 golden-master tests vs Excel Tab 05/06 outputs |
| `scripts/seed_ldf_ler.py` | Seeds LDF, retention, trend tables |
| `scripts/seed_state_rules.py` | Seeds 50 simulated state rules |
| `alembic/` | Migrations (`env.py` uses `app.models.Base.metadata`) |

---

## Rating Engine Details

The engine (`rate()` function) takes these **dataclass inputs**:

```python
AccountParams(
    named_insured, primary_state, effective_date, expiration_date,
    loss_valuation_date, csl=1e6, experience_cap=1e5,
    structure="Deductible", retention=0, schedule_mod=-0.08,
    full_credibility_claim_count=1084, fixed_expense_per_unit=85,
    expiring_premium_per_unit=3800
)
FleetExposureRow(state, vehicle_class, operating_radius,
    units_2022, units_2023, units_2024, units_2025,
    projected_units, projected_trailers)
LossOccurrenceRow(occurrence_id, loss_date, paid_indemnity,
    case_indemnity, paid_alae, case_alae,
    total_incurred, at_policy_limit, capped_loss, above_cap, policy_year)
```

Returns `QuoteResult` with:
- `experience_rating`: per-year LDF rows + `pooled_burn_cost` + `credibility`
- `state_pricing`: per-state premium breakdown
- `structure_comparison`: 10 rows (Deductible/SIR × 5 retentions) with LER, credits
- `summary`: selected structure's premium, tax, total payable, rate change

---

## Model Parameters (in `app/services/__init__.py`)

Currently in-memory dicts (placeholder for Supabase):
- `LDF_TABLE` — 7 age floors → limited LDF
- `RETENTION_TABLE` — 5 retentions × (deductible_ler, sir_ler, ded_fee, sir_fee)
- `TREND_FACTOR` — frequency, severity, combined
- `STATE_RULES` — 50 states with manual_capped_per_unit, excess_capped_ratio, variable_expense, profit_provision, min/max_mod, tax, surcharge, flat_charge

---

## Testing

All tests in `tests/test_rating_engine.py`:
```bash
pytest tests/test_rating_engine.py -v
```

Tests cover:
- Experience rating produces reasonable pooled burn cost
- Credibility bounded [0, 1]
- PA schedule mod clamped to -0.05 bound
- OH schedule mod within [-0.15, 0.15] → no clamp
- Structure comparison has 10 rows (2×5)
- Total payable = selected_premium + tax_charges + (surcharge_rate × selected_premium) + flat_charge

---

## Next Development Steps (from SPEC.md)

1. Wire `/api/v1/rate` to fetch model params from Supabase (not in-memory)
2. Complete `POST /api/v1/loss-run/upload` (CSV/Excel parsing in `app/services.py`)
3. Implement `QuoteStore` for quote persistence
4. Build HTMX templates (`app/templates/`) for 4-step UI
5. Run seed scripts against live Supabase
6. Alembic migration for initial schema

---

## Environment Variables (`.env`)

```bash
SUPABASE_URL=https://<project>.supabase.co
SUPABASE_KEY=<anon-key>
SUPABASE_DB_URL=postgresql+asyncpg://postgres:<password>@<host>:5432/postgres
SUPABASE_DB_PASSWORD=<password>
DEBUG=true
LOG_LEVEL=INFO
```

Copy `.env.example` → `.env` and fill in.