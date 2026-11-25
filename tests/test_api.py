"""Integration tests for the FastAPI endpoints using httpx AsyncClient."""

from __future__ import annotations

import io
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
def mock_params():
    """Return test model parameters."""
    return {
        "ldf_factors": [
            {"age_floor_months": 0, "limited_ldf": 2.5},
            {"age_floor_months": 12, "limited_ldf": 1.65},
            {"age_floor_months": 24, "limited_ldf": 1.28},
            {"age_floor_months": 36, "limited_ldf": 1.13},
            {"age_floor_months": 48, "limited_ldf": 1.06},
            {"age_floor_months": 60, "limited_ldf": 1.02},
            {"age_floor_months": 72, "limited_ldf": 1.0},
        ],
        "retention_factors": [
            {"retention": 0.0, "deductible_ler": 0.0, "sir_ler": 0.0, "ded_fee_per_unit": 0.0, "sir_fee_per_unit": 0.0},
            {"retention": 10_000.0, "deductible_ler": 0.12, "sir_ler": 0.12, "ded_fee_per_unit": 18.0, "sir_fee_per_unit": 5.0},
            {"retention": 25_000.0, "deductible_ler": 0.24, "sir_ler": 0.24, "ded_fee_per_unit": 28.0, "sir_fee_per_unit": 8.0},
            {"retention": 50_000.0, "deductible_ler": 0.37, "sir_ler": 0.37, "ded_fee_per_unit": 42.0, "sir_fee_per_unit": 12.0},
            {"retention": 100_000.0, "deductible_ler": 0.51, "sir_ler": 0.51, "ded_fee_per_unit": 65.0, "sir_fee_per_unit": 18.0},
        ],
        "trend_factor": {"frequency_trend": 0.005, "severity_trend": 0.055, "combined_trend": 0.060275},
        "state_rules": {
            "OH": {
                "state_code": "OH",
                "manual_capped_per_unit": 2150.0,
                "excess_capped_ratio": 0.45,
                "variable_expense": 0.19,
                "profit_provision": 0.055,
                "lcm_override": None,
                "applied_lcm": 1.3245033112582782,
                "min_mod": -0.15,
                "max_mod": 0.15,
                "lcr_confirmed": False,
                "waiver_allowed": False,
                "customer_tax_rate": 0.012,
                "surcharge_rate": 0.0025,
                "flat_charge": 20.0,
            },
            "PA": {
                "state_code": "PA",
                "manual_capped_per_unit": 2330.0,
                "excess_capped_ratio": 0.48,
                "variable_expense": 0.21,
                "profit_provision": 0.05,
                "lcm_override": None,
                "applied_lcm": 1.38,
                "min_mod": -0.05,
                "max_mod": 0.12,
                "lcr_confirmed": False,
                "waiver_allowed": False,
                "customer_tax_rate": 0.017,
                "surcharge_rate": 0.003,
                "flat_charge": 35.0,
            },
            "IN": {
                "state_code": "IN",
                "manual_capped_per_unit": 1920.0,
                "excess_capped_ratio": 0.41,
                "variable_expense": 0.18,
                "profit_provision": 0.055,
                "lcm_override": None,
                "applied_lcm": 1.3071895424836601,
                "min_mod": -0.10,
                "max_mod": 0.10,
                "lcr_confirmed": False,
                "waiver_allowed": False,
                "customer_tax_rate": 0.009,
                "surcharge_rate": 0.002,
                "flat_charge": 15.0,
            },
        },
    }


async def _mock_load(params):
    return params


@pytest.mark.asyncio
async def test_health_check() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "commercial-auto-rating"}


@pytest.mark.asyncio
async def test_rate_endpoint_returns_quote(mock_params) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        async def mock_load():
            return mock_params

        with patch(
            "app.main.load_model_parameters", new=mock_load
        ):
            payload = {
                "account": {
                    "named_insured": "Test Account",
                    "primary_state": "OH",
                    "effective_date": "2026-01-01",
                    "expiration_date": "2027-01-01",
                    "loss_valuation_date": "2026-01-01",
                    "csl": 1_000_000,
                    "experience_cap": 100_000,
                    "structure": "Deductible",
                    "retention": 25_000,
                    "schedule_mod": -0.08,
                    "full_credibility_claim_count": 1084,
                    "fixed_expense_per_unit": 85,
                    "expiring_premium_per_unit": 3_800,
                },
                "fleet_exposures": [
                    {
                        "state": "OH",
                        "vehicle_class": "Tractor",
                        "operating_radius": "Regional",
                        "units_2022": 29,
                        "units_2023": 31,
                        "units_2024": 33,
                        "units_2025": 34,
                        "projected_units": 36,
                        "projected_trailers": 48,
                    },
                ],
                "loss_occurrences": [
                    {
                        "occurrence_id": "OCC-1001",
                        "loss_date": "2022-01-03",
                        "paid_indemnity": 37_467,
                        "case_indemnity": 2_391,
                        "paid_alae": 2_670,
                        "case_alae": 996,
                    },
                ],
            }

            response = await client.post("/api/v1/rate", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert "quote_id" in data
    assert "experience_rating" in data
    assert "state_pricing" in data
    assert "structure_comparison" in data
    assert "summary" in data
    assert len(data["state_pricing"]) >= 1
    assert len(data["structure_comparison"]) == 10
    assert data["summary"]["selected_structure"] == "Deductible"
    assert data["summary"]["selected_retention"] == 25_000


@pytest.mark.asyncio
async def test_rate_endpoint_validation_error(mock_params) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        async def mock_load():
            return mock_params

        with patch(
            "app.main.load_model_parameters", new=mock_load
        ):
            payload = {
                "account": {
                    "primary_state": "OH",
                    "effective_date": "2026-01-01",
                    "expiration_date": "2027-01-01",
                    "loss_valuation_date": "2026-01-01",
                    "structure": "Deductible",
                },
                "fleet_exposures": [],
            }
            response = await client.post("/api/v1/rate", json=payload)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_loss_run_template_download() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/loss-run/template")
    assert response.status_code == 200
    assert (
        "spreadsheetml" in response.headers.get("content-type", "")
        or "ms-excel" in response.headers.get("content-type", "")
    )
    assert "attachment" in response.headers.get("content-disposition", "")


@pytest.mark.asyncio
async def test_loss_run_upload_csv(mock_params) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        csv_content = (
            "Occurrence ID,Loss Date,Valuation Date,Paid Indemnity,Case Indemnity,Paid ALAE,Case ALAE\n"
            "OCC-1001,2022-01-03,2026-01-01,37467,2391,2670,996\n"
            "OCC-1002,2022-02-04,2026-01-01,2969,190,212,79\n"
        )

        files = {
            "file": ("loss_run.csv", io.BytesIO(csv_content.encode()), "text/csv"),
        }
        data = {"account_id": "test-account-123"}

        response = await client.post(
            "/api/v1/loss-run/upload", files=files, data=data
        )

    assert response.status_code == 200
    body = response.json()
    assert body["parsed_count"] == 2
    assert len(body["occurrences"]) == 2


@pytest.mark.asyncio
async def test_loss_run_upload_invalid_file() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        files = {
            "file": ("test.txt", b"not a valid file", "text/plain"),
        }
        data = {"account_id": "test-account-123"}

        response = await client.post(
            "/api/v1/loss-run/upload", files=files, data=data
        )

    assert response.status_code == 415