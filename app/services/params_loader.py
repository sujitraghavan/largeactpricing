"""Load model parameters from Supabase database into rating-engine-ready format."""

from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy import select

from app.db import async_session_factory
from app.models import LDFFactorDB, RetentionFactorDB, StateRatingRuleDB, TrendFactorDB
from app.services.rating_engine import (
    LDFFactor,
    RetentionFactor,
    StateRatingRule,
    TrendFactor,
)


async def load_model_parameters() -> Dict[str, Any]:
    """Fetch all model parameters from Supabase into dicts for the rating engine.

    Returns a dict with keys: ldf_factors, retention_factors, trend_factor, state_rules
    """
    async with async_session_factory() as session:
        # LDF factors
        ldf_stmt = select(LDFFactorDB).order_by(LDFFactorDB.age_floor_months)
        ldf_result = await session.execute(ldf_stmt)
        ldf_factors = [
            LDFFactor(
                age_floor_months=r.age_floor_months,
                limited_ldf=r.limited_ldf,
            )
            for r in ldf_result.scalars().all()
        ]

        # Retention factors
        ret_stmt = select(RetentionFactorDB).order_by(RetentionFactorDB.retention)
        ret_result = await session.execute(ret_stmt)
        retention_factors = [
            RetentionFactor(
                retention=r.retention,
                deductible_ler=r.deductible_ler,
                sir_ler=r.sir_ler,
                ded_fee_per_unit=r.ded_fee_per_unit,
                sir_fee_per_unit=r.sir_fee_per_unit,
            )
            for r in ret_result.scalars().all()
        ]

        # Trend factor (single row)
        trend_stmt = select(TrendFactorDB)
        trend_result = await session.execute(trend_stmt)
        trend_row = trend_result.scalars().first()
        if trend_row:
            trend_factor = TrendFactor(
                frequency_trend=trend_row.frequency_trend,
                severity_trend=trend_row.severity_trend,
                combined_trend=trend_row.combined_trend,
            )
        else:
            trend_factor = TrendFactor(
                frequency_trend=0.005,
                severity_trend=0.055,
                combined_trend=0.060275,
            )

        # State rules
        state_stmt = select(StateRatingRuleDB)
        state_result = await session.execute(state_stmt)
        state_rules = {}
        for r in state_result.scalars().all():
            state_rules[r.state_code] = StateRatingRule(
                state_code=r.state_code,
                manual_capped_per_unit=r.manual_capped_per_unit,
                excess_capped_ratio=r.excess_capped_ratio,
                variable_expense=r.variable_expense,
                profit_provision=r.profit_provision,
                lcm_override=r.lcm_override,
                applied_lcm=r.applied_lcm,
                min_mod=r.min_mod,
                max_mod=r.max_mod,
                lcr_confirmed=r.lcr_confirmed,
                waiver_allowed=r.waiver_allowed,
                customer_tax_rate=r.customer_tax_rate,
                surcharge_rate=r.surcharge_rate,
                flat_charge=r.flat_charge,
            )

        return {
            "ldf_factors": ldf_factors,
            "retention_factors": retention_factors,
            "trend_factor": trend_factor,
            "state_rules": state_rules,
        }