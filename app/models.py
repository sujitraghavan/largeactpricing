"""Data models for the Commercial Auto Loss Rating Engine.

This module contains:
1. Pydantic models for API request/response validation
2. SQLAlchemy ORM models for Supabase / PostgreSQL tables
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import DeclarativeBase

# ---------------------------------------------------------------------------
# SQLAlchemy declarative base
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    """Declarative base for all SQLAlchemy ORM models."""


# ---------------------------------------------------------------------------
# --- SQLAlchemy ORM models ------------------------------------------------
# ---------------------------------------------------------------------------


class AccountDB(Base):
    """Account & policy terms per quote (Tab 01)."""

    __tablename__ = "accounts"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    named_insured = Column(Text, nullable=False)
    primary_state = Column(String(2), nullable=False)
    effective_date = Column(Date, nullable=False)
    expiration_date = Column(Date, nullable=False)
    loss_valuation_date = Column(Date, nullable=False)
    csl = Column(Float, nullable=False, default=1_000_000)
    experience_cap = Column(Float, nullable=False, default=100_000)
    structure = Column(String(20), nullable=False)  # "Deductible" or "SIR"
    retention = Column(Float, nullable=False, default=0)
    schedule_mod = Column(Float, nullable=False, default=-0.08)
    full_credibility_claim_count = Column(Float, nullable=False, default=1084)
    fixed_expense_per_unit = Column(Float, nullable=False, default=85)
    expiring_premium_per_unit = Column(Float, nullable=False, default=3_800)
    created_at = Column(DateTime, server_default=func.now())
    created_by = Column(Text)


class FleetExposureDB(Base):
    """Fleet exposure schedule row (Tab 02)."""

    __tablename__ = "fleet_exposures"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    account_id = Column(
        PG_UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False
    )
    state = Column(String(2), nullable=False)
    vehicle_class = Column(Text, nullable=False)
    operating_radius = Column(Text, nullable=False)
    units_2022 = Column(Float, nullable=False, default=0)
    units_2023 = Column(Float, nullable=False, default=0)
    units_2024 = Column(Float, nullable=False, default=0)
    units_2025 = Column(Float, nullable=False, default=0)
    projected_units = Column(Float, nullable=False, default=0)
    projected_trailers = Column(Float, nullable=False, default=0)


class LossOccurrenceDB(Base):
    """One occurrence row from the loss run (Tab 03)."""

    __tablename__ = "loss_occurrences"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    account_id = Column(
        PG_UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False
    )
    occurrence_id = Column(Text, nullable=False)
    loss_date = Column(Date, nullable=False)
    paid_indemnity = Column(Float, nullable=False, default=0)
    case_indemnity = Column(Float, nullable=False, default=0)
    paid_alae = Column(Float, nullable=False, default=0)
    case_alae = Column(Float, nullable=False, default=0)
    total_incurred = Column(Float, nullable=False)
    at_policy_limit = Column(Float, nullable=False)
    capped_loss = Column(Float, nullable=False)
    above_cap = Column(Float, nullable=False)
    policy_year = Column(Integer, nullable=False)


class LDFFactorDB(Base):
    """Limited Loss Development Factors by maturity age (Tab 04)."""

    __tablename__ = "ldf_factors"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    age_floor_months = Column(Integer, nullable=False, unique=True)
    limited_ldf = Column(Float, nullable=False)


class RetentionFactorDB(Base):
    """LER and fee per unit by retention level (Tab 04)."""

    __tablename__ = "retention_factors"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    retention = Column(Float, nullable=False, unique=True)
    deductible_ler = Column(Float, nullable=False)
    sir_ler = Column(Float, nullable=False)
    ded_fee_per_unit = Column(Float, nullable=False)
    sir_fee_per_unit = Column(Float, nullable=False)


class TrendFactorDB(Base):
    """Frequency, severity, and combined trend factors (Tab 04)."""

    __tablename__ = "trend_factors"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    frequency_trend = Column(Float, nullable=False, default=0.005)
    severity_trend = Column(Float, nullable=False, default=0.055)
    combined_trend = Column(Float, nullable=False, default=0.060275)


class StateRatingRuleDB(Base):
    """Per-state rating rules — all 50 states seeded at deploy."""

    __tablename__ = "state_rating_rules"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    state_code = Column(String(2), nullable=False, unique=True)
    manual_capped_per_unit = Column(Float, nullable=False)
    excess_capped_ratio = Column(Float, nullable=False)
    variable_expense = Column(Float, nullable=False)
    profit_provision = Column(Float, nullable=False)
    lcm_override = Column(Float, nullable=True)  # NULL => compute from ve+pp
    applied_lcm = Column(Float, nullable=False)  # final applied LCM factor
    min_mod = Column(Float, nullable=False)
    max_mod = Column(Float, nullable=False)
    lcr_confirmed = Column(Boolean, nullable=False, default=False)
    waiver_allowed = Column(Boolean, nullable=False, default=False)
    customer_tax_rate = Column(Float, nullable=False, default=0.012)
    surcharge_rate = Column(Float, nullable=False, default=0.0025)
    flat_charge = Column(Float, nullable=False, default=20)


class QuoteDB(Base):
    """Stored quote output from the rating engine."""

    __tablename__ = "quotes"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    account_id = Column(
        PG_UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False
    )
    experience_rating = Column(JSONB, nullable=False)
    state_pricing = Column(JSONB, nullable=False)
    structure_comparison = Column(JSONB, nullable=False)
    summary = Column(JSONB, nullable=False)
    selected_structure = Column(Text, nullable=False)
    selected_retention = Column(Float, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    created_by = Column(Text)

# ---------------------------------------------------------------------------
# --- Pydantic models (API request/response) -------------------------------
# ---------------------------------------------------------------------------


STRUCTURE_CHOICES = ["Deductible", "SIR"]
RETENTION_LEVELS = [0, 10_000, 25_000, 50_000, 100_000]


class FleetExposureIn(BaseModel):
    """One row from the Fleet Exposure Schedule."""

    state: str = Field(..., description="Garaging state abbreviation")
    vehicle_class: str = Field(
        ..., description="Vehicle class (e.g. Heavy truck, Tractor)"
    )
    operating_radius: str = Field(
        ..., description="Operating radius (Local, Regional)"
    )
    units_2022: float = Field(ge=0, description="Earned unit years 2022")
    units_2023: float = Field(ge=0, description="Earned unit years 2023")
    units_2024: float = Field(ge=0, description="Earned unit years 2024")
    units_2025: float = Field(ge=0, description="Earned unit years 2025")
    projected_units: float = Field(
        ge=0, description="Projected units for quote period"
    )
    projected_trailers: float = Field(
        ge=0, description="Projected trailers (descriptive only)"
    )


class LossOccurrenceIn(BaseModel):
    """One row from the Loss Run (ground-up occurrence)."""

    occurrence_id: str = Field(..., description="Unique occurrence ID")
    loss_date: date = Field(..., description="Date of loss")
    paid_indemnity: float = Field(ge=0, description="Paid indemnity")
    case_indemnity: float = Field(ge=0, description="Case indemnity")
    paid_alae: float = Field(ge=0, description="Paid ALAE")
    case_alae: float = Field(ge=0, description="Case ALAE")

    @property
    def total_incurred(self) -> float:
        return (
            self.paid_indemnity
            + self.case_indemnity
            + self.paid_alae
            + self.case_alae
        )


class AccountTermsIn(BaseModel):
    """Account & policy terms — the editable inputs from Tab 01."""

    named_insured: str
    primary_state: str
    effective_date: date
    expiration_date: date
    loss_valuation_date: date
    csl: float = Field(default=1_000_000, ge=1)
    experience_cap: float = Field(default=100_000, ge=1)
    structure: str = Field(..., description="Deductible or SIR")
    retention: float = Field(default=0, ge=0)
    schedule_mod: float = Field(default=-0.08)
    full_credibility_claim_count: float = Field(default=1084, ge=1)
    fixed_expense_per_unit: float = Field(default=85, ge=0)
    expiring_premium_per_unit: float = Field(default=3_800, ge=0)


class RateRequest(BaseModel):
    """Full request body for the rating endpoint."""

    account: AccountTermsIn
    fleet_exposures: List[FleetExposureIn]
    loss_occurrences: Optional[List[LossOccurrenceIn]] = None
    loss_run_file_id: Optional[str] = None

    @model_validator(mode="after")
    def check_loss_input(self) -> "RateRequest":
        lo = self.loss_occurrences
        lrfi = self.loss_run_file_id
        if lo is None and lrfi is None:
            raise ValueError(
                "Either loss_occurrences or loss_run_file_id must be provided"
            )
        return self
        lo = values.get("loss_occurrences")
        lrfi = values.get("loss_run_file_id")
        if lo is None and lrfi is None:
            raise ValueError(
                "Either loss_occurrences or loss_run_file_id must be provided"
            )
        return values


# --- Output models --------------------------------------------------------


class LDFRowOut(BaseModel):
    policy_year: int
    unit_years: float
    occurrences: int
    capped_incurred: float
    age_months: int
    limited_ldf: float
    ultimate_capped: float
    trend_years: float
    trended_ultimate: float
    burn_cost_per_unit: float


class ExperienceRatingOut(BaseModel):
    by_year: List[LDFRowOut]
    pooled_burn_cost: float
    credibility: float


class StatePricingRowOut(BaseModel):
    state: str
    projected_units: float
    manual_capped: float
    blended_capped: float
    excess_per_unit: float
    ground_up_per_unit: float
    schedule_mod: float
    schedule_check: str
    applied_lcm: float
    tax_rate: float
    surcharge_rate: float
    flat_charge: float
    selected_premium: float
    tax_charges: float
    total_payable: float


class StructureComparisonRowOut(BaseModel):
    structure: str
    retention: float
    ler: float
    technical_premium: float
    credit_vs_zero: float
    credit_pct: float
    total_payable: float


class QuoteSummaryOut(BaseModel):
    selected_structure: str
    selected_retention: float
    technical_premium: float
    tax_and_charges: float
    total_payable: float
    premium_per_unit: float
    rate_change_vs_expiring: float


class RateResponse(BaseModel):
    quote_id: str
    account: AccountTermsIn
    experience_rating: ExperienceRatingOut
    state_pricing: List[StatePricingRowOut]
    structure_comparison: List[StructureComparisonRowOut]
    summary: QuoteSummaryOut
    created_at: datetime

    model_config = {"protected_namespaces": ()}