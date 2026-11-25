# Commercial Auto Loss Rating Engine

An online rating model for commercial auto liability insurance, ported from
the `Commercial_Auto_Loss_Rating.xlsx` Excel workbook.

## Tech Stack

- **Backend:** Python / FastAPI
- **Database:** Supabase (PostgreSQL via SQLAlchemy + asyncpg)
- **Frontend:** HTMX + Jinja2 (v0.1) / React (planned)
- **Data:** Pydantic validation, SQLAlchemy ORM, Alembic migrations

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Set SUPABASE_URL, SUPABASE_KEY, SUPABASE_DB_URL

# Run migrations (alembic upgrade head)
alembic upgrade head

# Seed model parameters
python scripts/seed_ldf_ler.py
python scripts/seed_state_rules.py

# Run tests
pytest tests/

# Start the server
uvicorn app.main:app --reload
```

## API Endpoints

- `POST /api/v1/rate` — Run the full rating calculation
- `GET /api/v1/loss-run/template` — Download loss-run Excel template
- `POST /api/v1/loss-run/upload` — Upload loss run (CSV/Excel)
- `GET /api/v1/quotes/{quote_id}` — Retrieve a stored quote
- `GET /health` — Health check

## Rating Engine

The core calculation chain lives in `app/services/rating_engine.py`:

1. **Experience Rating** (Tabs 05): per-policy-year LDF, trend, pooled burn cost, credibility
2. **State Pricing** (Tabs 05→06): manual capped → blended capped → excess → schedule mod → LCM → premium
3. **Structure Comparison**: Deductible / SIR × retention → LER → credit analysis

## Database Schema

- `accounts` — Account & policy terms per quote
- `fleet_exposures` — Fleet exposure schedule rows
- `loss_occurrences` — Occurrence-level loss data
- `ldf_factors` — Limited LDF by maturity age
- `retention_factors` — LER + fees by retention
- `trend_factors` — Frequency / severity / combined trends
- `state_rating_rules` — All 50 state rating rules
- `quotes` — Stored quote outputs (JSONB)

## Testing

- `tests/test_rating_engine.py` — Golden-master tests against Excel outputs

## Spec

See [SPEC.md](./SPEC.md) for the full product specification.
