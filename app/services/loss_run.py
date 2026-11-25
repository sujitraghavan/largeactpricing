"""Loss run parser — CSV / Excel upload → validated loss occurrence rows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, List

import io
import openpyxl
import pandas as pd


@dataclass
class ParsedLossRun:
    """Result of parsing a loss run file."""

    rows: List[dict]
    errors: List[str]


REQUIRED_COLUMNS = {
    "Occurrence ID",
    "Loss Date",
    "Paid Indemnity",
    "Case Indemnity",
    "Paid ALAE",
    "Case ALAE",
}


def parse_loss_run_file(file_bytes: bytes, filename: str) -> ParsedLossRun:
    """Parse a CSV or Excel file into loss occurrence rows.

    Expected columns (exact names, case-sensitive):
      Occurrence ID, Loss Date, Valuation Date, Paid Indemnity,
      Case Indemnity, Paid ALAE, Case ALAE

    Returns a ParsedLossRun with validated rows and any errors.
    """
    errors: List[str] = []
    rows: List[dict] = []

    try:
        if filename.lower().endswith(".csv"):
            df = pd.read_csv(io.BytesIO(file_bytes))
        else:
            df = pd.read_excel(io.BytesIO(file_bytes))
    except Exception as e:
        return ParsedLossRun([], [f"Failed to read file: {e}"])

    # Normalize column names (strip whitespace)
    df.columns = [c.strip() for c in df.columns]

    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        errors.append(f"Missing required columns: {', '.join(sorted(missing))}")
        return ParsedLossRun([], errors)

    # Keep only required + optional valuation date
    keep_cols = list(REQUIRED_COLUMNS) + ["Valuation Date"]
    df = df[keep_cols]

    for idx, row in df.iterrows():
        try:
            occ_id = str(row["Occurrence ID"]).strip()
            loss_date = pd.to_datetime(row["Loss Date"]).date()

            paid_ind = float(row["Paid Indemnity"])
            case_ind = float(row["Case Indemnity"])
            paid_alae = float(row["Paid ALAE"])
            case_alae = float(row["Case ALAE"])

            if any(v < 0 for v in [paid_ind, case_ind, paid_alae, case_alae]):
                errors.append(f"Row {idx+2}: negative amount not allowed")
                continue

            valuation_date = None
            if pd.notna(row.get("Valuation Date")):
                valuation_date = pd.to_datetime(row["Valuation Date"]).date()

            rows.append(
                {
                    "occurrence_id": occ_id,
                    "loss_date": loss_date,
                    "valuation_date": valuation_date,
                    "paid_indemnity": paid_ind,
                    "case_indemnity": case_ind,
                    "paid_alae": paid_alae,
                    "case_alae": case_alae,
                }
            )
        except Exception as e:
            errors.append(f"Row {idx+2}: {e}")

    # Check for duplicate occurrence IDs
    seen = set()
    for r in rows:
        if r["occurrence_id"] in seen:
            errors.append(f"Duplicate occurrence ID: {r['occurrence_id']}")
        seen.add(r["occurrence_id"])

    return ParsedLossRun(rows=rows, errors=errors)


def generate_loss_run_template() -> bytes:
    """Generate an Excel template for loss-run upload."""
    import io

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Loss Run Template"

    headers = [
        "Occurrence ID",
        "Loss Date",
        "Valuation Date",
        "Paid Indemnity",
        "Case Indemnity",
        "Paid ALAE",
        "Case ALAE",
    ]
    ws.append(headers)

    # Example rows
    example_rows = [
        ("OCC-1001", "2022-01-03", "2026-01-01", 37_467, 2_391, 2_670, 996),
        ("OCC-1002", "2022-02-04", "2026-01-01", 2_969, 190, 212, 79),
        ("OCC-1003", "2022-03-05", "2026-01-01", 197_400, 12_600, 14_070, 5_250),
    ]
    for row in example_rows:
        ws.append(list(row))

    # Style header
    for cell in ws[1]:
        cell.font = openpyxl.styles.Font(bold=True)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()