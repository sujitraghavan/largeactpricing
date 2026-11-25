"""Quote persistence service — stores full rating results in Supabase."""

from __future__ import annotations

from typing import Any, Dict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import async_session_factory
from app.models import (
    AccountDB,
    FleetExposureDB,
    LossOccurrenceDB,
    QuoteDB,
)


class QuoteStore:
    """CRUD for quotes using async SQLAlchemy sessions."""

    def __init__(self, session_factory=None):
        self._session_factory = session_factory or async_session_factory

    async def save_quote(self, account_data: Dict[str, Any], result_dict: Dict[str, Any], created_by: str = "underwriter") -> UUID:
        """Save account + rating result to Supabase, return quote ID."""
        async with self._session_factory() as session:
            # Upsert account
            account = AccountDB(
                named_insured=account_data.get("named_insured", ""),
                primary_state=account_data.get("primary_state", "OH"),
                effective_date=account_data.get("effective_date") and __import__("datetime").datetime.fromisoformat(account_data.get("effective_date")).date() or __import__("datetime").date(2026, 1, 1),
                expiration_date=account_data.get("expiration_date") and __import__("datetime").datetime.fromisoformat(account_data.get("expiration_date")).date() or __import__("datetime").date(2027, 1, 1),
                loss_valuation_date=account_data.get("loss_valuation_date") and __import__("datetime").datetime.fromisoformat(account_data.get("loss_valuation_date")).date() or __import__("datetime").date(2026, 1, 1),
                csl=account_data.get("csl") or 1_000_000.0,
                experience_cap=account_data.get("experience_cap") or 100_000.0,
                structure=account_data.get("structure", "Deductible"),
                retention=account_data.get("retention") or 0.0,
                schedule_mod=account_data.get("schedule_mod") or -0.08,
                full_credibility_claim_count=account_data.get("full_credibility_claim_count") or 1084.0,
                fixed_expense_per_unit=account_data.get("fixed_expense_per_unit") or 85.0,
                expiring_premium_per_unit=account_data.get("expiring_premium_per_unit") or 3_800.0,
                created_by=created_by,
            )
            session.add(account)
            await session.flush()

            account_id = account.id

            # Save fleet exposures
            for fe in account_data.get("fleet_exposures", []):
                session.add(
                    FleetExposureDB(
                        account_id=account_id,
                        state=fe.get("state", "OH"),
                        vehicle_class=fe.get("vehicle_class", ""),
                        operating_radius=fe.get("operating_radius", "Local"),
                        units_2022=fe.get("units_2022") or 0.0,
                        units_2023=fe.get("units_2023") or 0.0,
                        units_2024=fe.get("units_2024") or 0.0,
                        units_2025=fe.get("units_2025") or 0.0,
                        projected_units=fe.get("projected_units") or 0.0,
                        projected_trailers=fe.get("projected_trailers") or 0.0,
                    )
                )

            # Save loss occurrences
            for lo in account_data.get("loss_occurrences", []):
                session.add(
                    LossOccurrenceDB(
                        account_id=account_id,
                        occurrence_id=lo.get("occurrence_id", ""),
                        loss_date=lo.get("loss_date") and __import__("datetime").datetime.fromisoformat(lo.get("loss_date")).date() or __import__("datetime").date(2022, 1, 1),
                        paid_indemnity=lo.get("paid_indemnity") or 0.0,
                        case_indemnity=lo.get("case_indemnity") or 0.0,
                        paid_alae=lo.get("paid_alae") or 0.0,
                        case_alae=lo.get("case_alae") or 0.0,
                        total_incurred=lo.get("total_incurred") or 0.0,
                        at_policy_limit=lo.get("at_policy_limit") or 0.0,
                        capped_loss=lo.get("capped_loss") or 0.0,
                        above_cap=lo.get("above_cap") or 0.0,
                        policy_year=lo.get("policy_year") or 2022,
                    )
                )

            # Save quote
            quote = QuoteDB(
                account_id=account_id,
                experience_rating=result_dict.get("experience_rating", {}),
                state_pricing=result_dict.get("state_pricing", []),
                structure_comparison=result_dict.get("structure_comparison", []),
                summary=result_dict.get("summary", {}),
                selected_structure=account_data.get("structure", "Deductible"),
                selected_retention=account_data.get("retention") or 0.0,
            )
            session.add(quote)
            await session.commit()
            await session.refresh(quote)
            return quote.id

    async def get_quote(self, quote_id: str) -> Dict[str, Any]:
        """Retrieve a quote by ID."""
        async with self._session_factory() as session:
            stmt = select(QuoteDB).where(QuoteDB.id == quote_id)
            result = await session.execute(stmt)
            quote = result.scalar_one_or_none()
            if quote is None:
                return None
            return {
                "id": str(quote.id),
                "account_id": str(quote.account_id),
                "experience_rating": quote.experience_rating,
                "state_pricing": quote.state_pricing,
                "structure_comparison": quote.structure_comparison,
                "summary": quote.summary,
                "selected_structure": quote.selected_structure,
                "selected_retention": quote.selected_retention,
            }
