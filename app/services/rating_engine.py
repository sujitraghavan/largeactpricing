"""Pure-Python rating engine for Commercial Auto Loss Rating.

This module contains zero framework dependencies.  It is the port of the
actuarial calculation chain from ``Commercial_Auto_Loss_Rating.xlsx``
(tabs 01‒06) into a testable function::

    rate(account, fleet_exposures, loss_occurrences, params) -> QuoteResult

All monetary amounts are in USD.  All factors are plain floats.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from math import sqrt
from typing import Any, Dict, List, Optional
from uuid import uuid4

# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


@dataclass
class AccountParams:
    """Account & policy terms (Tab 01)."""

    named_insured: str
    primary_state: str
    effective_date: date
    expiration_date: date
    loss_valuation_date: date
    csl: float = 1_000_000.0
    experience_cap: float = 100_000.0
    structure: str = "Deductible"  # "Deductible" or "SIR"
    retention: float = 0.0
    schedule_mod: float = -0.08
    full_credibility_claim_count: float = 1084.0
    fixed_expense_per_unit: float = 85.0
    expiring_premium_per_unit: float = 3_800.0


@dataclass
class FleetExposureRow:
    """One fleet exposure schedule row (Tab 02)."""

    state: str
    vehicle_class: str
    operating_radius: str
    units_2022: float = 0.0
    units_2023: float = 0.0
    units_2024: float = 0.0
    units_2025: float = 0.0
    projected_units: float = 0.0
    projected_trailers: float = 0.0


@dataclass
class LossOccurrenceRow:
    """One occurrence row from the loss run (Tab 03)."""

    occurrence_id: str
    loss_date: date
    paid_indemnity: float = 0.0
    case_indemnity: float = 0.0
    paid_alae: float = 0.0
    case_alae: float = 0.0
    total_incurred: float = 0.0
    at_policy_limit: float = 0.0
    capped_loss: float = 0.0
    above_cap: float = 0.0
    policy_year: int = 0


@dataclass
class LDFFactor:
    age_floor_months: int
    limited_ldf: float


@dataclass
class RetentionFactor:
    retention: float
    deductible_ler: float
    sir_ler: float
    ded_fee_per_unit: float
    sir_fee_per_unit: float


@dataclass
class TrendFactor:
    frequency_trend: float = 0.005
    severity_trend: float = 0.055
    combined_trend: float = 0.060275


@dataclass
class StateRatingRule:
    state_code: str
    manual_capped_per_unit: float
    excess_capped_ratio: float
    variable_expense: float
    profit_provision: float
    lcm_override: Optional[float] = None
    applied_lcm: float = 1.0
    min_mod: float = -0.15
    max_mod: float = 0.15
    lcr_confirmed: bool = False
    waiver_allowed: bool = False
    customer_tax_rate: float = 0.012
    surcharge_rate: float = 0.0025
    flat_charge: float = 20.0


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class LDFRow:
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


@dataclass
class ExperienceRatingResult:
    by_year: List[LDFRow] = field(default_factory=list)
    pooled_burn_cost: float = 0.0
    credibility: float = 0.0


@dataclass
class StatePricingRow:
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


@dataclass
class StructureComparisonRow:
    structure: str
    retention: float
    ler: float
    technical_premium: float
    credit_vs_zero: float
    credit_pct: float
    total_payable: float


@dataclass
class QuoteSummary:
    selected_structure: str
    selected_retention: float
    technical_premium: float
    tax_and_charges: float
    total_payable: float
    premium_per_unit: float
    rate_change_vs_expiring: float


@dataclass
class QuoteResult:
    quote_id: str
    account: AccountParams
    experience_rating: ExperienceRatingResult
    state_pricing: List[StatePricingRow]
    structure_comparison: List[StructureComparisonRow]
    summary: QuoteSummary
    created_at: datetime


# ---------------------------------------------------------------------------
# Policy-year helper
# ---------------------------------------------------------------------------

POLICY_YEARS = [2022, 2023, 2024, 2025]


def _year_midpoint(year: int) -> date:
    """Return 1 July of the given policy year."""
    return date(year, 7, 1)


def _months_between(valuation: date, midpoint: date) -> int:
    """Months from valuation date backwards to policy-year midpoint (floor)."""
    delta_days = (valuation - midpoint).days
    return int(delta_days // 30.4375)


# ---------------------------------------------------------------------------
# Model-parameter lookups
# ---------------------------------------------------------------------------

def _as_ldf_obj(f: Any) -> LDFFactor:
    if isinstance(f, dict):
        return LDFFactor(
            age_floor_months=int(f.get("age_floor_months", 0)),
            limited_ldf=float(f.get("limited_ldf", 1.0)),
        )
    return f


def _as_retention_obj(f: Any) -> RetentionFactor:
    if isinstance(f, dict):
        return RetentionFactor(
            retention=float(f.get("retention", 0.0)),
            deductible_ler=float(f.get("deductible_ler", 0.0)),
            sir_ler=float(f.get("sir_ler", 0.0)),
            ded_fee_per_unit=float(f.get("ded_fee_per_unit", 0.0)),
            sir_fee_per_unit=float(f.get("sir_fee_per_unit", 0.0)),
        )
    return f


def _select_ldf(ldf_factors: List[Any], age_months: int) -> float:
    """Pick LDF using largest age_floor_months <= age_months."""
    ldf_objs = [_as_ldf_obj(f) for f in ldf_factors]
    eligible = [f for f in ldf_objs if f.age_floor_months <= age_months]
    if not eligible:
        return ldf_objs[0].limited_ldf
    best = max(eligible, key=lambda f: f.age_floor_months)
    return best.limited_ldf


def _select_retention(
    retention_factors: List[Any], retention: float
) -> RetentionFactor:
    """Exact-match lookup for retention level."""
    ret_objs = [_as_retention_obj(f) for f in retention_factors]
    for f in ret_objs:
        if abs(f.retention - retention) < 1e-9:
            return f
    raise ValueError(f"No retention factor for retention={retention}")


# ---------------------------------------------------------------------------
# Main rating function
# ---------------------------------------------------------------------------

def rate(
    account: AccountParams,
    fleet_exposures: List[FleetExposureRow],
    loss_occurrences: List[LossOccurrenceRow],
    ldf_factors: List[LDFFactor],
    retention_factors: List[RetentionFactor],
    trend_factor: TrendFactor,
    state_rules: Dict[str, StateRatingRule],
) -> QuoteResult:
    """Run the full commercial auto loss rating calculation.

    Implements the calculation chain from tabs 04‒06 of the Excel workbook:

    1. Experience rating per policy year (LDF, trend, burn cost)
    2. Pooled burn cost + credibility
    3. State-level pricing (manual capped → blended capped → excess →
       schedule mod → LCM → per-state premium + taxes)
    4. Structure comparison (Deductible / SIR × retention levels)
    """

    # ------------------------------------------------------------------
    # Step 1: Aggregate exposures & losses per policy year
    # ------------------------------------------------------------------
    unit_years_by_year: Dict[int, float] = {y: 0.0 for y in POLICY_YEARS}
    occurrences_by_year: Dict[int, int] = {y: 0 for y in POLICY_YEARS}
    capped_incurred_by_year: Dict[int, float] = {y: 0.0 for y in POLICY_YEARS}

    for row in fleet_exposures:
        unit_years_by_year[2022] += row.units_2022
        unit_years_by_year[2023] += row.units_2023
        unit_years_by_year[2024] += row.units_2024
        unit_years_by_year[2025] += row.units_2025

    for occ in loss_occurrences:
        py = occ.policy_year
        if py in occurrences_by_year:
            occurrences_by_year[py] += 1
            capped_incurred_by_year[py] += occ.capped_loss

    total_unit_years = sum(unit_years_by_year.values())
    total_occurrences = sum(occurrences_by_year.values())

    # ------------------------------------------------------------------
    # Step 2: Experience rating per policy year
    # ------------------------------------------------------------------
    ldf_rows: List[LDFRow] = []
    valuation_date = account.loss_valuation_date

    for year in POLICY_YEARS:
        unit_years = unit_years_by_year[year]
        occurrences = occurrences_by_year[year]
        capped_incurred = capped_incurred_by_year[year]

        midpoint = _year_midpoint(year)
        age_months = _months_between(valuation_date, midpoint)

        # Excel uses fixed ages: 48/36/24/12 for 2022-2025 with a 2026-01-01
        # valuation.  Fall back to computed months if zero.
        if age_months <= 0:
            age_months = {2022: 48, 2023: 36, 2024: 24, 2025: 12}[year]

        limited_ldf = _select_ldf(ldf_factors, age_months)
        ultimate_capped = capped_incurred * limited_ldf

        trend_years = (account.effective_date - midpoint).days / 365.25
        combined_trend = (
            trend_factor.get("combined_trend", 0.060275)
            if isinstance(trend_factor, dict)
            else trend_factor.combined_trend
        )
        trended_ultimate = ultimate_capped * (
            (1.0 + combined_trend) ** trend_years
        )

        burn_cost_per_unit = (
            trended_ultimate / unit_years if unit_years > 0 else 0.0
        )

        ldf_rows.append(
            LDFRow(
                policy_year=year,
                unit_years=unit_years,
                occurrences=occurrences,
                capped_incurred=capped_incurred,
                age_months=age_months,
                limited_ldf=limited_ldf,
                ultimate_capped=ultimate_capped,
                trend_years=trend_years,
                trended_ultimate=trended_ultimate,
                burn_cost_per_unit=burn_cost_per_unit,
            )
        )

    # ------------------------------------------------------------------
    # Step 3: Pooled burn cost & credibility
    # ------------------------------------------------------------------
    weighted_burn = 0.0
    total_weight = 0.0
    for row in ldf_rows:
        if row.unit_years > 0:
            weighted_burn += row.burn_cost_per_unit * row.unit_years
            total_weight += row.unit_years

    pooled_burn_cost = weighted_burn / total_weight if total_weight > 0 else 0.0

    credibility = min(
        1.0,
        sqrt(total_occurrences / account.full_credibility_claim_count),
    )

    experience_rating = ExperienceRatingResult(
        by_year=ldf_rows,
        pooled_burn_cost=pooled_burn_cost,
        credibility=credibility,
    )

    # ------------------------------------------------------------------
    # Step 4: Ground-up total (needed for structure comparison)
    # ------------------------------------------------------------------
    # Build state rules lookup once, computing applied LCM where missing.
    state_rules_resolved: Dict[str, StateRatingRule] = {}
    for code, rule in state_rules.items():
        # Normalize both dict-based rules and StateRatingRule objects
        if isinstance(rule, StateRatingRule):
            rule_obj = StateRatingRule(
                state_code=rule.state_code,
                manual_capped_per_unit=float(rule.manual_capped_per_unit),
                excess_capped_ratio=float(rule.excess_capped_ratio),
                variable_expense=float(rule.variable_expense),
                profit_provision=float(rule.profit_provision),
                lcm_override=rule.lcm_override,
                applied_lcm=float(
                    rule.applied_lcm
                    if rule.applied_lcm is not None
                    else (
                        (1.0 + rule.variable_expense + rule.profit_provision)
                        / (1.0 - rule.variable_expense - rule.profit_provision)
                        if (1.0 - rule.variable_expense - rule.profit_provision) != 0
                        else 1.0
                    )
                ),
                min_mod=float(rule.min_mod),
                max_mod=float(rule.max_mod),
                lcr_confirmed=bool(rule.lcr_confirmed),
                waiver_allowed=bool(rule.waiver_allowed),
                customer_tax_rate=float(rule.customer_tax_rate),
                surcharge_rate=float(rule.surcharge_rate),
                flat_charge=float(rule.flat_charge),
            )
        else:
            rule_obj = StateRatingRule(
                state_code=code,
                manual_capped_per_unit=float(
                    rule.get("manual_capped_per_unit", 0.0)
                ),
                excess_capped_ratio=float(
                    rule.get("excess_capped_ratio", 0.0)
                ),
                variable_expense=float(rule.get("variable_expense", 0.0)),
                profit_provision=float(rule.get("profit_provision", 0.0)),
                lcm_override=rule.get("lcm_override"),
                applied_lcm=float(
                    rule.get("applied_lcm", (1.0 + rule.get("variable_expense", 0) + rule.get("profit_provision", 0)) / (1.0 - rule.get("variable_expense", 0) - rule.get("profit_provision", 0)))
                ),
                min_mod=float(rule.get("min_mod", -0.15)),
                max_mod=float(rule.get("max_mod", 0.15)),
                lcr_confirmed=bool(rule.get("lcr_confirmed", False)),
                waiver_allowed=bool(rule.get("waiver_allowed", False)),
                customer_tax_rate=float(rule.get("customer_tax_rate", 0.012)),
                surcharge_rate=float(rule.get("surcharge_rate", 0.0025)),
                flat_charge=float(rule.get("flat_charge", 20.0)),
            )
        state_rules_resolved[code] = rule_obj

    # ------------------------------------------------------------------
    # Step 5: State-level pricing
    # ------------------------------------------------------------------
    state_rows: List[StatePricingRow] = []
    total_projected_units = 0.0
    total_ground_up_per_unit_units = 0.0  # sum(ground_up/unit * projected_units)

    # Order states as they appear in fleet_exposures, dedup preserving order
    seen_states: List[str] = []
    for row in fleet_exposures:
        if row.state not in seen_states:
            seen_states.append(row.state)
        total_projected_units += row.projected_units

    for state_code in seen_states:
        rule = state_rules_resolved.get(state_code)
        if rule is None:
            # No state rule found — skip (or could raise).  Skip keeps the
            # engine robust for demo data.
            continue

        projected_units = sum(
            r.projected_units for r in fleet_exposures if r.state == state_code
        )
        if projected_units <= 0:
            continue

        manual_capped = rule.manual_capped_per_unit

        # Blended capped = credibility × pooled burn cost + (1 − cred) × manual
        blended_capped = (
            credibility * pooled_burn_cost + (1.0 - credibility) * manual_capped
        )

        excess_per_unit = blended_capped * rule.excess_capped_ratio
        ground_up_per_unit = blended_capped + excess_per_unit

        # Schedule mod with bounds
        schedule_mod = account.schedule_mod
        schedule_check = "Within rules"
        if not (rule.lcr_confirmed and rule.waiver_allowed):
            if schedule_mod < rule.min_mod:
                schedule_mod = rule.min_mod
                schedule_check = "Bound applied"
            elif schedule_mod > rule.max_mod:
                schedule_mod = rule.max_mod
                schedule_check = "Bound applied"

        applied_lcm = rule.applied_lcm

        state_selected_premium = (
            ground_up_per_unit
            * projected_units
            * (1.0 + schedule_mod)
            * applied_lcm
        )

        tax_charges = state_selected_premium * rule.customer_tax_rate
        surcharge = state_selected_premium * rule.surcharge_rate
        total_payable = (
            state_selected_premium + tax_charges + surcharge + rule.flat_charge
        )

        state_rows.append(
            StatePricingRow(
                state=state_code,
                projected_units=projected_units,
                manual_capped=manual_capped,
                blended_capped=blended_capped,
                excess_per_unit=excess_per_unit,
                ground_up_per_unit=ground_up_per_unit,
                schedule_mod=schedule_mod,
                schedule_check=schedule_check,
                applied_lcm=applied_lcm,
                tax_rate=rule.customer_tax_rate,
                surcharge_rate=rule.surcharge_rate,
                flat_charge=rule.flat_charge,
                selected_premium=state_selected_premium,
                tax_charges=tax_charges,
                total_payable=total_payable,
            )
        )

        total_ground_up_per_unit_units += ground_up_per_unit * projected_units

    # ------------------------------------------------------------------
    # Step 6: Structure comparison (Deductible / SIR × retention levels)
    # ------------------------------------------------------------------
    structure_rows: List[StructureComparisonRow] = []

    # Technical premium at $0 retention (first-dollar) used for credit baseline.
    zero_retention_premiums: Dict[str, float] = {}

    for structure in ["Deductible", "SIR"]:
        for retention_level in [0, 10_000, 25_000, 50_000, 100_000]:
            retention_factor_obj = _select_retention(
                retention_factors, retention_level
            )
            ler = (
                retention_factor_obj.deductible_ler
                if structure == "Deductible"
                else retention_factor_obj.sir_ler
            )
            fee_per_unit = (
                retention_factor_obj.ded_fee_per_unit
                if structure == "Deductible"
                else retention_factor_obj.sir_fee_per_unit
            )

            # Technical premium per state: base premium × (1 − LER) + fee
            tech_premium = 0.0
            tax_total = 0.0
            surcharge_total = 0.0
            flat_total = 0.0

            for row in state_rows:
                state_prem_after_ler = row.selected_premium * (1.0 - ler)
                tech_premium += state_prem_after_ler

                tax_total += row.tax_charges
                surcharge_total += row.surcharge_rate * row.selected_premium
                flat_total += row.flat_charge

            tech_premium += fee_per_unit * total_projected_units

            zero_key = f"{structure}|{retention_level}"
            zero_retention_premiums[zero_key] = tech_premium

            total_payable = (
                tech_premium + tax_total + surcharge_total + flat_total
            )

            structure_rows.append(
                StructureComparisonRow(
                    structure=structure,
                    retention=retention_level,
                    ler=ler,
                    technical_premium=tech_premium,
                    credit_vs_zero=0.0,  # filled below
                    credit_pct=0.0,
                    total_payable=total_payable,
                )
            )

    # Fill credit vs $0 (baseline = first-dollar at same structure)
    zero_baseline: Dict[str, float] = {}
    for row in structure_rows:
        if row.retention == 0:
            zero_baseline[row.structure] = row.technical_premium

    for row in structure_rows:
        baseline = zero_baseline[row.structure]
        if baseline > 0:
            row.credit_vs_zero = baseline - row.technical_premium
            row.credit_pct = row.credit_vs_zero / baseline
        else:
            row.credit_vs_zero = 0.0
            row.credit_pct = 0.0

    # ------------------------------------------------------------------
    # Step 7: Summary for the selected structure / retention
    # ------------------------------------------------------------------
    selected_row = next(
        r
        for r in structure_rows
        if r.structure == account.structure
        and abs(r.retention - account.retention) < 1e-9
    )

    tax_total = sum(r.tax_charges for r in state_rows)
    surcharge_total = sum(r.surcharge_rate * r.selected_premium for r in state_rows)
    flat_total = sum(r.flat_charge for r in state_rows)

    summary = QuoteSummary(
        selected_structure=account.structure,
        selected_retention=account.retention,
        technical_premium=selected_row.technical_premium,
        tax_and_charges=tax_total + surcharge_total,
        total_payable=selected_row.total_payable,
        premium_per_unit=(
            selected_row.technical_premium / total_projected_units
            if total_projected_units > 0
            else 0.0
        ),
        rate_change_vs_expiring=(
            (selected_row.technical_premium / total_projected_units)
            / account.expiring_premium_per_unit
            - 1.0
            if total_projected_units > 0 and account.expiring_premium_per_unit > 0
            else 0.0
        ),
    )

    return QuoteResult(
        quote_id=str(uuid4()),
        account=account,
        experience_rating=experience_rating,
        state_pricing=state_rows,
        structure_comparison=structure_rows,
        summary=summary,
        created_at=datetime.utcnow(),
    )


# ---------------------------------------------------------------------------
# Convenience: dataclass → dict helpers (for JSONB storage / API response)
# ---------------------------------------------------------------------------

def _dataclass_to_dict(obj: Any) -> Any:
    if isinstance(obj, list):
        return [_dataclass_to_dict(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _dataclass_to_dict(v) for k, v in obj.items()}
    if hasattr(obj, "__dataclass_fields__"):
        return {
            k: _dataclass_to_dict(getattr(obj, k)) for k in obj.__dataclass_fields__
        }
    return obj


def quote_result_to_dict(result: QuoteResult) -> Dict[str, Any]:
    """Convert a QuoteResult to a plain dict suitable for JSONB storage."""
    return _dataclass_to_dict(result)
