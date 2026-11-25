"""Services package for the Commercial Auto Loss Rating Engine."""

from app.services.rating_engine import (
    rate,
    AccountParams,
    FleetExposureRow,
    LossOccurrenceRow,
    LDFFactor,
    RetentionFactor,
    TrendFactor,
    StateRatingRule,
    QuoteResult,
    ExperienceRatingResult,
    StatePricingRow,
    StructureComparisonRow,
    QuoteSummary,
)

# ════════════════════════════════════════════════════════════════════════════
# Model parameters (in-memory placeholder until Supabase wiring is complete)
# These match the values from SPEC.md section 9 — 50-state simulated rules.
# ════════════════════════════════════════════════════════════════════════════

LDF_TABLE = [
    {"age_floor_months": 0, "limited_ldf": 2.5},
    {"age_floor_months": 12, "limited_ldf": 1.65},
    {"age_floor_months": 24, "limited_ldf": 1.28},
    {"age_floor_months": 36, "limited_ldf": 1.13},
    {"age_floor_months": 48, "limited_ldf": 1.06},
    {"age_floor_months": 60, "limited_ldf": 1.02},
    {"age_floor_months": 72, "limited_ldf": 1.0},
]

RETENTION_TABLE = [
    {"retention": 0.0, "deductible_ler": 0.0, "sir_ler": 0.0, "ded_fee_per_unit": 0.0, "sir_fee_per_unit": 0.0},
    {"retention": 10_000.0, "deductible_ler": 0.12, "sir_ler": 0.12, "ded_fee_per_unit": 18.0, "sir_fee_per_unit": 5.0},
    {"retention": 25_000.0, "deductible_ler": 0.24, "sir_ler": 0.24, "ded_fee_per_unit": 28.0, "sir_fee_per_unit": 8.0},
    {"retention": 50_000.0, "deductible_ler": 0.37, "sir_ler": 0.37, "ded_fee_per_unit": 42.0, "sir_fee_per_unit": 12.0},
    {"retention": 100_000.0, "deductible_ler": 0.51, "sir_ler": 0.51, "ded_fee_per_unit": 65.0, "sir_fee_per_unit": 18.0},
]

TREND_FACTOR = {"frequency_trend": 0.005, "severity_trend": 0.055, "combined_trend": 0.060275}

STATE_RULES = {
    "AL": {"manual_capped_per_unit": 2_150, "excess_capped_ratio": 0.44, "variable_expense": 0.20, "profit_provision": 0.052},
    "AK": {"manual_capped_per_unit": 2_200, "excess_capped_ratio": 0.46, "variable_expense": 0.21, "profit_provision": 0.053},
    "AZ": {"manual_capped_per_unit": 1_980, "excess_capped_ratio": 0.42, "variable_expense": 0.19, "profit_provision": 0.050},
    "AR": {"manual_capped_per_unit": 1_950, "excess_capped_ratio": 0.41, "variable_expense": 0.18, "profit_provision": 0.049},
    "CA": {"manual_capped_per_unit": 2_350, "excess_capped_ratio": 0.48, "variable_expense": 0.21, "profit_provision": 0.055},
    "CO": {"manual_capped_per_unit": 2_050, "excess_capped_ratio": 0.43, "variable_expense": 0.195, "profit_provision": 0.051},
    "CT": {"manual_capped_per_unit": 2_100, "excess_capped_ratio": 0.44, "variable_expense": 0.20, "profit_provision": 0.052},
    "DE": {"manual_capped_per_unit": 2_000, "excess_capped_ratio": 0.43, "variable_expense": 0.19, "profit_provision": 0.050},
    "FL": {"manual_capped_per_unit": 2_250, "excess_capped_ratio": 0.47, "variable_expense": 0.205, "profit_provision": 0.054},
    "GA": {"manual_capped_per_unit": 2_080, "excess_capped_ratio": 0.45, "variable_expense": 0.20, "profit_provision": 0.053},
    "HI": {"manual_capped_per_unit": 2_180, "excess_capped_ratio": 0.45, "variable_expense": 0.20, "profit_provision": 0.053},
    "ID": {"manual_capped_per_unit": 1_920, "excess_capped_ratio": 0.41, "variable_expense": 0.18, "profit_provision": 0.048},
    "IL": {"manual_capped_per_unit": 2_200, "excess_capped_ratio": 0.46, "variable_expense": 0.205, "profit_provision": 0.053},
    "IN": {"manual_capped_per_unit": 1_920, "excess_capped_ratio": 0.41, "variable_expense": 0.18, "profit_provision": 0.048},
    "IA": {"manual_capped_per_unit": 1_970, "excess_capped_ratio": 0.42, "variable_expense": 0.19, "profit_provision": 0.050},
    "KS": {"manual_capped_per_unit": 1_930, "excess_capped_ratio": 0.41, "variable_expense": 0.18, "profit_provision": 0.049},
    "KY": {"manual_capped_per_unit": 2_030, "excess_capped_ratio": 0.43, "variable_expense": 0.19, "profit_provision": 0.051},
    "LA": {"manual_capped_per_unit": 2_300, "excess_capped_ratio": 0.47, "variable_expense": 0.205, "profit_provision": 0.054},
    "ME": {"manual_capped_per_unit": 2_020, "excess_capped_ratio": 0.43, "variable_expense": 0.19, "profit_provision": 0.051},
    "MD": {"manual_capped_per_unit": 2_130, "excess_capped_ratio": 0.45, "variable_expense": 0.20, "profit_provision": 0.052},
    "MA": {"manual_capped_per_unit": 2_160, "excess_capped_ratio": 0.44, "variable_expense": 0.20, "profit_provision": 0.052},
    "MI": {"manual_capped_per_unit": 2_080, "excess_capped_ratio": 0.45, "variable_expense": 0.20, "profit_provision": 0.053},
    "MN": {"manual_capped_per_unit": 1_990, "excess_capped_ratio": 0.42, "variable_expense": 0.19, "profit_provision": 0.050},
    "MS": {"manual_capped_per_unit": 2_010, "excess_capped_ratio": 0.42, "variable_expense": 0.19, "profit_provision": 0.050},
    "MO": {"manual_capped_per_unit": 2_040, "excess_capped_ratio": 0.43, "variable_expense": 0.195, "profit_provision": 0.051},
    "MT": {"manual_capped_per_unit": 2_050, "excess_capped_ratio": 0.43, "variable_expense": 0.195, "profit_provision": 0.051},
    "NE": {"manual_capped_per_unit": 1_960, "excess_capped_ratio": 0.42, "variable_expense": 0.19, "profit_provision": 0.050},
    "NV": {"manual_capped_per_unit": 2_120, "excess_capped_ratio": 0.44, "variable_expense": 0.20, "profit_provision": 0.052},
    "NH": {"manual_capped_per_unit": 2_030, "excess_capped_ratio": 0.43, "variable_expense": 0.19, "profit_provision": 0.051},
    "NJ": {"manual_capped_per_unit": 2_320, "excess_capped_ratio": 0.48, "variable_expense": 0.21, "profit_provision": 0.055},
    "NM": {"manual_capped_per_unit": 1_940, "excess_capped_ratio": 0.41, "variable_expense": 0.185, "profit_provision": 0.049},
    "NY": {"manual_capped_per_unit": 2_400, "excess_capped_ratio": 0.49, "variable_expense": 0.215, "profit_provision": 0.056},
    "NC": {"manual_capped_per_unit": 2_020, "excess_capped_ratio": 0.43, "variable_expense": 0.195, "profit_provision": 0.051},
    "ND": {"manual_capped_per_unit": 1_980, "excess_capped_ratio": 0.42, "variable_expense": 0.19, "profit_provision": 0.050},
    "OH": {"manual_capped_per_unit": 2_150, "excess_capped_ratio": 0.45, "variable_expense": 0.19, "profit_provision": 0.050},
    "OK": {"manual_capped_per_unit": 1_970, "excess_capped_ratio": 0.42, "variable_expense": 0.19, "profit_provision": 0.050},
    "OR": {"manual_capped_per_unit": 2_010, "excess_capped_ratio": 0.42, "variable_expense": 0.19, "profit_provision": 0.050},
    "PA": {"manual_capped_per_unit": 2_330, "excess_capped_ratio": 0.48, "variable_expense": 0.21, "profit_provision": 0.055},
    "RI": {"manual_capped_per_unit": 2_040, "excess_capped_ratio": 0.43, "variable_expense": 0.195, "profit_provision": 0.051},
    "SC": {"manual_capped_per_unit": 1_990, "excess_capped_ratio": 0.42, "variable_expense": 0.19, "profit_provision": 0.050},
    "SD": {"manual_capped_per_unit": 1_960, "excess_capped_ratio": 0.42, "variable_expense": 0.19, "profit_provision": 0.050},
    "TN": {"manual_capped_per_unit": 2_070, "excess_capped_ratio": 0.44, "variable_expense": 0.20, "profit_provision": 0.052},
    "TX": {"manual_capped_per_unit": 2_200, "excess_capped_ratio": 0.46, "variable_expense": 0.205, "profit_provision": 0.053},
    "UT": {"manual_capped_per_unit": 2_030, "excess_capped_ratio": 0.43, "variable_expense": 0.195, "profit_provision": 0.051},
    "VT": {"manual_capped_per_unit": 2_000, "excess_capped_ratio": 0.43, "variable_expense": 0.19, "profit_provision": 0.050},
    "VA": {"manual_capped_per_unit": 2_110, "excess_capped_ratio": 0.45, "variable_expense": 0.20, "profit_provision": 0.052},
    "WA": {"manual_capped_per_unit": 2_080, "excess_capped_ratio": 0.45, "variable_expense": 0.20, "profit_provision": 0.053},
    "WV": {"manual_capped_per_unit": 2_020, "excess_capped_ratio": 0.43, "variable_expense": 0.19, "profit_provision": 0.051},
    "WI": {"manual_capped_per_unit": 2_000, "excess_capped_ratio": 0.43, "variable_expense": 0.19, "profit_provision": 0.050},
    "WY": {"manual_capped_per_unit": 2_070, "excess_capped_ratio": 0.44, "variable_expense": 0.20, "profit_provision": 0.052},
}

__all__ = [
    "rate",
    "AccountParams",
    "FleetExposureRow",
    "LossOccurrenceRow",
    "LDFFactor",
    "RetentionFactor",
    "TrendFactor",
    "StateRatingRule",
    "LDF_TABLE",
    "RETENTION_TABLE",
    "TREND_FACTOR",
    "STATE_RULES",
]
