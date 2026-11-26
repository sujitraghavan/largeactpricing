"""Seed script: 50 state rating rules (simulated from OH/PA/IN + regional adjustments).

All values are simulated but realistic.  In production, actuaries will review
and override via DB updates or admin UI (future iteration).
"""

from __future__ import annotations

import asyncio

from typing import Any, Dict

from dotenv import load_dotenv

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.models import Base, StateRatingRuleDB
from app.services import STATE_RULES


async def seed() -> None:
    """Seed all 50 state rating rules."""
    from app.config import settings

    engine = create_async_engine(settings.supabase_db_url, echo=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        # Clear existing rules (idempotent re-seed)
        await session.execute(StateRatingRuleDB.__table__.delete())

        for code, rule in STATE_RULES.items():
            session.add(
                StateRatingRuleDB(
                    state_code=code,
                    manual_capped_per_unit=rule["manual_capped_per_unit"],
                    excess_capped_ratio=rule["excess_capped_ratio"],
                    variable_expense=rule["variable_expense"],
                    profit_provision=rule["profit_provision"],
                    lcm_override=rule.get("lcm_override"),
                    applied_lcm=rule.get(
                        "applied_lcm",
                        (1.0 + rule.get("variable_expense", 0) + rule.get("profit_provision", 0))
                        / (1.0 - rule.get("variable_expense", 0) - rule.get("profit_provision", 0))
                    ),
                    min_mod=rule.get("min_mod", -0.15),
                    max_mod=rule.get("max_mod", 0.15),
                    lcr_confirmed=rule.get("lcr_confirmed", False),
                    waiver_allowed=rule.get("waiver_allowed", False),
                    customer_tax_rate=rule.get("customer_tax_rate", 0.012),
                    surcharge_rate=rule.get("surcharge_rate", 0.0025),
                    flat_charge=rule.get("flat_charge", 20),
                )
            )

        await session.commit()
        print(f"✅ Seeded {len(STATE_RULES)} state rating rules")


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(seed())