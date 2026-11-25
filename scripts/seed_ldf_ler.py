"""Seed script: LDF, retention, and trend factors (Tab 04)."""

from __future__ import annotations

import asyncio
import os

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.models import (
    LDFFactorDB,
    RetentionFactorDB,
    TrendFactorDB,
    Base,
)


async def seed() -> None:
    """Seed the three core model parameter tables."""
    from app.config import settings

    engine = create_async_engine(settings.supabase_db_url, echo=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        # --- LDF factors ---
        session.add_all(
            [
                LDFFactorDB(age_floor_months=0, limited_ldf=2.5),
                LDFFactorDB(age_floor_months=12, limited_ldf=1.65),
                LDFFactorDB(age_floor_months=24, limited_ldf=1.28),
                LDFFactorDB(age_floor_months=36, limited_ldf=1.13),
                LDFFactorDB(age_floor_months=48, limited_ldf=1.06),
                LDFFactorDB(age_floor_months=60, limited_ldf=1.02),
                LDFFactorDB(age_floor_months=72, limited_ldf=1.0),
            ]
        )

        # --- Retention factors ---
        session.add_all(
            [
                RetentionFactorDB(
                    retention=0,
                    deductible_ler=0,
                    sir_ler=0,
                    ded_fee_per_unit=0,
                    sir_fee_per_unit=0,
                ),
                RetentionFactorDB(
                    retention=10_000,
                    deductible_ler=0.12,
                    sir_ler=0.12,
                    ded_fee_per_unit=18,
                    sir_fee_per_unit=5,
                ),
                RetentionFactorDB(
                    retention=25_000,
                    deductible_ler=0.24,
                    sir_ler=0.24,
                    ded_fee_per_unit=28,
                    sir_fee_per_unit=8,
                ),
                RetentionFactorDB(
                    retention=50_000,
                    deductible_ler=0.37,
                    sir_ler=0.37,
                    ded_fee_per_unit=42,
                    sir_fee_per_unit=12,
                ),
                RetentionFactorDB(
                    retention=100_000,
                    deductible_ler=0.51,
                    sir_ler=0.51,
                    ded_fee_per_unit=65,
                    sir_fee_per_unit=18,
                ),
            ]
        )

        # --- Trend factor ---
        session.add(
            TrendFactorDB(
                frequency_trend=0.005,
                severity_trend=0.055,
                combined_trend=0.060275,
            )
        )

        await session.commit()
        print("✅ Seeded LDF, retention, and trend factors")


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(seed())