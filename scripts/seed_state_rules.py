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
                    state_code=rule.state_code,
                    manual_capped_per_unit=rule.manual_capped_per_unit,
                    excess_capped_ratio=rule.excess_capped_ratio,
                    variable_expense=rule.variable_expense,
                    profit_provision=rule.profit_provision,
                    lcm_override=rule.lcm_override,
                    applied_lcm=rule.applied_lcm,
                    min_mod=rule.min_mod,
                    max_mod=rule.max_mod,
                    lcr_confirmed=rule.lcr_confirmed,
                    waiver_allowed=rule.waiver_allowed,
                    customer_tax_rate=rule.customer_tax_rate,
                    surcharge_rate=rule.surcharge_rate,
                    flat_charge=rule.flat_charge,
                )
            )

        await session.commit()
        print(f"✅ Seeded {len(STATE_RULES)} state rating rules")


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(seed())
