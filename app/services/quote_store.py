"""Quote persistence service — stores full rating results in Supabase."""

from __future__ import annotations

from typing import Any, Dict, List
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

    def _to_float(self, val: Any, default: float = 0.0) -> float:
        """Safely convert string/number to float."""
        if val is None or val == "":
            return default
        try:
            return float(val)
        except (ValueError, TypeError):
            return default

    def _to_int(self, val: Any, default: int = 0) -> int:
        """Safely convert string/number to int."""
        if val is None or val == "":
            return default
        try:
            return int(float(val))
        except (ValueError, TypeError):
            return default

    def _parse_date(self, val: Any, default: "date") -> "date":
        """Parse ISO date string to date object."""
        if not val:
            return default
        try:
            return __import__("datetime").datetime.fromisoformat(str(val)).date()
        except (ValueError, TypeError):
            return default

    async def save_quote(self, account_data: Dict[str, Any], result_dict: Dict[str, Any], created_by: str = "underwriter") -> UUID:
        """Save account + rating result to Supabase, return quote ID."""
        from datetime import date
        async with self._session_factory() as session:
            # Upsert account
            account = AccountDB(
                named_insured=account_data.get("named_insured", ""),
                primary_state=account_data.get("primary_state", "OH"),
                effective_date=self._parse_date(account_data.get("effective_date"), date(2026, 1, 1)),
                expiration_date=self._parse_date(account_data.get("expiration_date"), date(2027, 1, 1)),
                loss_valuation_date=self._parse_date(account_data.get("loss_valuation_date"), date(2026, 1, 1)),
                csl=self._to_float(account_data.get("csl"), 1_000_000.0),
                experience_cap=self._to_float(account_data.get("experience_cap"), 100_000.0),
                structure=account_data.get("structure", "Deductible"),
                retention=self._to_float(account_data.get("retention"), 0.0),
                schedule_mod=self._to_float(account_data.get("schedule_mod"), -0.08),
                full_credibility_claim_count=self._to_float(account_data.get("full_credibility_claim_count"), 1084.0),
                fixed_expense_per_unit=self._to_float(account_data.get("fixed_expense_per_unit"), 85.0),
                expiring_premium_per_unit=self._to_float(account_data.get("expiring_premium_per_unit"), 3_800.0),
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
                        units_2022=self._to_float(fe.get("units_2022"), 0.0),
                        units_2023=self._to_float(fe.get("units_2023"), 0.0),
                        units_2024=self._to_float(fe.get("units_2024"), 0.0),
                        units_2025=self._to_float(fe.get("units_2025"), 0.0),
                        projected_units=self._to_float(fe.get("projected_units"), 0.0),
                        projected_trailers=self._to_float(fe.get("projected_trailers"), 0.0),
                    )
                )

            # Save loss occurrences
            for lo in account_data.get("loss_occurrences", []):
                session.add(
                    LossOccurrenceDB(
                        account_id=account_id,
                        occurrence_id=lo.get("occurrence_id", ""),
                        loss_date=self._parse_date(lo.get("loss_date"), date(2022, 1, 1)),
                        paid_indemnity=self._to_float(lo.get("paid_indemnity"), 0.0),
                        case_indemnity=self._to_float(lo.get("case_indemnity"), 0.0),
                        paid_alae=self._to_float(lo.get("paid_alae"), 0.0),
                        case_alae=self._to_float(lo.get("case_alae"), 0.0),
                        total_incurred=self._to_float(lo.get("total_incurred"), 0.0),
                        at_policy_limit=self._to_float(lo.get("at_policy_limit"), 0.0),
                        capped_loss=self._to_float(lo.get("capped_loss"), 0.0),
                        above_cap=self._to_float(lo.get("above_cap"), 0.0),
                        policy_year=self._to_int(lo.get("policy_year"), 2022),
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
                selected_retention=self._to_float(account_data.get("retention"), 0.0),
            )
            session.add(quote)
            await session.commit()
            await session.refresh(quote)
            return quote.id

    async def get_quote(self, quote_id: str) -> Dict[str, Any]:
        """Retrieve a quote by ID."""
        async with self._session_factory() as session:
            stmt = (
                select(QuoteDB, AccountDB)
                .join(AccountDB, QuoteDB.account_id == AccountDB.id)
                .where(QuoteDB.id == quote_id)
            )
            result = await session.execute(stmt)
            row = result.one_or_none()
            if row is None:
                return None
            quote, account = row
            return {
                "id": str(quote.id),
                "named_insured": account.named_insured,
                "primary_state": account.primary_state,
                "experience_rating": quote.experience_rating,
                "state_pricing": quote.state_pricing,
                "structure_comparison": quote.structure_comparison,
                "summary": quote.summary,
                "selected_structure": quote.selected_structure,
                "selected_retention": quote.selected_retention,
                "created_at": quote.created_at.isoformat() if quote.created_at else None,
            }

    async def list_quotes(self, limit: int = 50) -> List[Dict[str, Any]]:
        """List recent quotes with summary info."""
        from sqlalchemy import desc
        from app.models import AccountDB
        async with self._session_factory() as session:
            stmt = (
                select(QuoteDB, AccountDB)
                .join(AccountDB, QuoteDB.account_id == AccountDB.id)
                .order_by(desc(QuoteDB.created_at))
                .limit(limit)
            )
            result = await session.execute(stmt)
            rows = result.all()
            return [
                {
                    "id": str(quote.id),
                    "named_insured": account.named_insured,
                    "primary_state": account.primary_state,
                    "selected_structure": quote.selected_structure,
                    "selected_retention": quote.selected_retention,
                    "total_payable": (quote.summary or {}).get("total_payable", 0),
                    "created_at": quote.created_at.isoformat() if quote.created_at else None,
                }
                for quote, account in rows
            ]
