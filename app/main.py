"""FastAPI application for the Commercial Auto Loss Rating Engine."""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Dict, List

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.models import AccountTermsIn, RateRequest
from app.services.quote_store import QuoteStore
from app.services.loss_run import generate_loss_run_template, parse_loss_run_file
from app.services.params_loader import load_model_parameters
from app.services.rating_engine import (
    AccountParams,
    FleetExposureRow,
    LossOccurrenceRow,
    QuoteResult,
    rate,
    quote_result_to_dict,
)

# ── Direct Jinja2 environment (bypasses Starlette TemplateResponse bugs on Python 3.14) ──
env = Environment(
    loader=FileSystemLoader("app/templates"),
    autoescape=select_autoescape(),
)

app = FastAPI(
    title="Commercial Auto Loss Rating Engine",
    description=(
        "Online rating model for commercial auto liability. "
        "Port of actuarial calculation chain from Commercial_Auto_Loss_Rating.xlsx"
    ),
    version="0.1.0",
)


@app.on_event("startup")
async def on_startup() -> None:
    return None


def render_template(name: str, context: Dict[str, Any]) -> HTMLResponse:
    """Render a template using Jinja2 directly, bypassing Starlette's TemplateResponse."""
    template = env.get_template(name)
    html = template.render(**context)
    return HTMLResponse(html)


# ── HTMX UI routes ────────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def step1(request: Request) -> HTMLResponse:
    """Render the first step (Account Terms)."""
    return render_template("step1_account.html", {"request": request})


@app.get("/step/2", response_class=HTMLResponse)
async def step2(request: Request) -> HTMLResponse:
    """Render the second step (Fleet Exposures)."""
    return render_template("step2_fleet.html", {"request": request})


@app.get("/step/3", response_class=HTMLResponse)
async def step3(request: Request) -> HTMLResponse:
    """Render the third step (Loss Run)."""
    return render_template("step3_loss_run.html", {"request": request})


@app.get("/step/4", response_class=HTMLResponse)
async def step4(request: Request) -> HTMLResponse:
    """Render the fourth step (Review & Rate)."""
    return render_template("step4_results.html", {"request": request})


# ── JSON API endpoints ────────────────────────────────────────────────────


@app.post("/api/v1/rate")
async def rate_quote(payload: RateRequest) -> Dict[str, Any]:
    """Run the full rating engine and return structured quote data as JSON."""
    model = await load_model_parameters()
    ldf_factors = model["ldf_factors"]
    retention_factors = model["retention_factors"]
    trend_factor = model["trend_factor"]
    state_rules = model["state_rules"]

    account = AccountParams(
        named_insured=payload.account.named_insured,
        primary_state=payload.account.primary_state,
        effective_date=payload.account.effective_date,
        expiration_date=payload.account.expiration_date,
        loss_valuation_date=payload.account.loss_valuation_date,
        csl=payload.account.csl,
        experience_cap=payload.account.experience_cap,
        structure=payload.account.structure,
        retention=payload.account.retention,
        schedule_mod=payload.account.schedule_mod,
        full_credibility_claim_count=payload.account.full_credibility_claim_count,
        fixed_expense_per_unit=payload.account.fixed_expense_per_unit,
        expiring_premium_per_unit=payload.account.expiring_premium_per_unit,
    )

    fleet_rows: List[FleetExposureRow] = []
    for fe in payload.fleet_exposures:
        fleet_rows.append(
            FleetExposureRow(
                state=fe.state,
                vehicle_class=fe.vehicle_class,
                operating_radius=fe.operating_radius,
                units_2022=fe.units_2022,
                units_2023=fe.units_2023,
                units_2024=fe.units_2024,
                units_2025=fe.units_2025,
                projected_units=fe.projected_units,
                projected_trailers=fe.projected_trailers,
            )
        )

    loss_rows: List[LossOccurrenceRow] = []
    if payload.loss_occurrences:
        for lo in payload.loss_occurrences:
            total_incurred = lo.paid_indemnity + lo.case_indemnity + lo.paid_alae + lo.case_alae
            policy_year = lo.loss_date.year
            if policy_year not in [2022, 2023, 2024, 2025]:
                policy_year = min(max(policy_year, 2022), 2025)

            loss_rows.append(
                LossOccurrenceRow(
                    occurrence_id=lo.occurrence_id,
                    loss_date=lo.loss_date,
                    paid_indemnity=lo.paid_indemnity,
                    case_indemnity=lo.case_indemnity,
                    paid_alae=lo.paid_alae,
                    case_alae=lo.case_alae,
                    total_incurred=total_incurred,
                    at_policy_limit=min(total_incurred, account.csl),
                    capped_loss=min(total_incurred, account.experience_cap),
                    above_cap=max(0.0, total_incurred - account.experience_cap),
                    policy_year=policy_year,
                )
            )

    result: QuoteResult = rate(
        account=account,
        fleet_exposures=fleet_rows,
        loss_occurrences=loss_rows,
        ldf_factors=ldf_factors,
        retention_factors=retention_factors,
        trend_factor=trend_factor,
        state_rules=state_rules,
    )

    return quote_result_to_dict(result)


# ── Loss run upload / template endpoints ─────────────────────────────────


@app.get("/api/v1/loss-run/template")
async def loss_run_template() -> Response:
    """Download an Excel template for loss-run upload."""
    content = generate_loss_run_template()
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="loss_run_template.xlsx"'
        },
    )


@app.post("/api/v1/loss-run/upload")
async def loss_run_upload(
    file: UploadFile = File(...),
    account_id: str = Form(...),
) -> Dict[str, Any]:
    """Upload a loss run file (CSV or Excel) and return parsed occurrences."""
    if file.content_type not in (
        "text/csv",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
        "application/octet-stream",
    ):
        raise HTTPException(status_code=415, detail="Unsupported file type")

    file_bytes = await file.read()
    parsed = parse_loss_run_file(file_bytes, file.filename or "loss_run")

    if parsed.errors:
        raise HTTPException(status_code=422, detail=parsed.errors)

    occurrences = []
    for row in parsed.rows:
        total_incurred = (
            row["paid_indemnity"] + row["case_indemnity"] + row["paid_alae"] + row["case_alae"]
        )
        policy_year = row["loss_date"].year if row["loss_date"] else None
        if policy_year is None or policy_year < 2022 or policy_year > 2025:
            policy_year = min(max(policy_year or 2022, 2022), 2025)

        occurrences.append(
            {
                "occurrence_id": row["occurrence_id"],
                "loss_date": row["loss_date"].isoformat() if row["loss_date"] else None,
                "valuation_date": row["valuation_date"].isoformat() if row["valuation_date"] else None,
                "paid_indemnity": row["paid_indemnity"],
                "case_indemnity": row["case_indemnity"],
                "paid_alae": row["paid_alae"],
                "case_alae": row["case_alae"],
                "total_incurred": total_incurred,
                "at_policy_limit": min(total_incurred, 1_000_000.0),
                "capped_loss": min(total_incurred, 100_000.0),
                "above_cap": max(0.0, total_incurred - 100_000.0),
                "policy_year": policy_year,
            }
        )

    return {
        "account_id": account_id,
        "parsed_count": len(occurrences),
        "occurrences": occurrences,
        "errors": parsed.errors,
    }


# ── Quote retrieval ───────────────────────────────────────────────────────


@app.get("/api/v1/quotes/{quote_id}")
async def get_quote(quote_id: str) -> Dict[str, Any]:
    """Retrieve a previously stored quote."""
    store = QuoteStore()
    quote = await store.get_quote(quote_id)
    if quote is None:
        raise HTTPException(status_code=404, detail="Quote not found")
    return quote


@app.post("/api/v1/quotes/save")
async def save_quote(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Persist a full quote (account data + rating result) to Supabase."""
    store = QuoteStore()
    account_data = payload.get("account", {})
    result_dict = payload.get("result", {})
    try:
        quote_id = await store.save_quote(account_data, result_dict)
        return {"quote_id": str(quote_id), "status": "saved"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Health ────────────────────────────────────────────────────────────────


@app.get("/health")
async def health_check() -> Dict[str, str]:
    return {"status": "ok", "service": "commercial-auto-rating"}