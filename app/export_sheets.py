"""
Export Layer — Google Sheets
------------------------------
Uses a free Google service account (no paid API tier required) via gspread.
Setup: create a service account in Google Cloud Console, enable the Sheets
API, download the JSON key to `credentials/service_account.json`, and share
your target Google Sheet with the service account's email address.
"""
import json
import logging
import os

import gspread
from google.oauth2.service_account import Credentials

from app.config import settings
from app.database import Invoice

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

FLAT_HEADERS = ["Invoice Number", "Vendor Name", "Customer Name", "Invoice Date",
                "Due Date", "Currency", "Subtotal", "Tax Amount", "Total Amount", "Status"]

LINE_ITEM_HEADERS = ["Invoice Number", "Description", "Quantity", "Unit Price", "Line Total"]


def _get_client():
    # Prefer inline JSON content (set as env var on cloud deployments like Railway)
    if settings.google_service_account_json_content:
        try:
            content = settings.google_service_account_json_content.strip()
            if content.startswith("'") and content.endswith("'"):
                content = content[1:-1]
            info = json.loads(content)
        except json.JSONDecodeError as e:
            raise ValueError(
                "GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT is set but is not valid JSON. "
                "In Railway, paste the full service account JSON object as the variable value. "
                f"Details: {e}"
            )
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
        return gspread.authorize(creds)

    # Fall back to file path (local dev with credentials/service_account.json)
    creds_path = settings.google_service_account_json
    if not os.path.exists(creds_path):
        raise FileNotFoundError(
            f"Service account credentials not found. "
            f"For local dev: place the JSON at '{creds_path}'. "
            f"For Railway/cloud: set GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT to the full "
            f"contents of the service account JSON file, because local credential files "
            f"are not deployed with the backend."
        )
    creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
    return gspread.authorize(creds)


def _get_or_create_worksheet(sh, title: str, headers: list[str]) -> gspread.Worksheet:
    try:
        ws = sh.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=title, rows=1000, cols=len(headers) + 2)
    return ws


def _ensure_headers(ws: gspread.Worksheet, headers: list[str]) -> None:
    """Write headers to row 1 only if the sheet is brand new (row 1 is empty)."""
    try:
        existing = ws.row_values(1)
    except Exception:
        existing = []

    if not existing or not any(v.strip() for v in existing):
        ws.insert_row(headers, index=1)


def _safe(val) -> str:
    """Convert None / floats to plain strings so gspread never drops a cell."""
    if val is None:
        return ""
    return str(val)


def export_invoice_to_sheets(invoice: Invoice, file_url: str = ""):
    client = _get_client()
    sh = client.open_by_key(settings.google_sheet_id)

    # ── Invoices sheet ──────────────────────────────────────────────────────────
    ws = _get_or_create_worksheet(sh, "Invoices", FLAT_HEADERS)
    _ensure_headers(ws, FLAT_HEADERS)

    row = [
        _safe(invoice.invoice_number),
        _safe(invoice.vendor_name),
        _safe(invoice.customer_name),
        _safe(invoice.invoice_date),
        _safe(invoice.due_date),
        _safe(invoice.currency),
        _safe(invoice.subtotal),
        _safe(invoice.tax_amount),
        _safe(invoice.total_amount),
        invoice.status.replace("_", " ").title() if invoice.status else "",
    ]

    # append_row always adds after the last populated row — no empty-row scan needed
    ws.append_row(row, value_input_option="USER_ENTERED")
    logger.info(f"Appended invoice {invoice.id} to Google Sheets 'Invoices' tab")

    # ── Line Items sheet (only in normalized mode) ───────────────────────────────
    if settings.sheets_mode == "normalized" and invoice.line_items_json:
        items_ws = _get_or_create_worksheet(sh, "Line Items", LINE_ITEM_HEADERS)
        _ensure_headers(items_ws, LINE_ITEM_HEADERS)

        try:
            items = json.loads(invoice.line_items_json)
        except json.JSONDecodeError:
            items = []

        for item in items:
            items_ws.append_row([
                _safe(invoice.invoice_number),
                _safe(item.get("description")),
                _safe(item.get("quantity")),
                _safe(item.get("unit_price")),
                _safe(item.get("line_total")),
            ], value_input_option="USER_ENTERED")

    return True


def check_sheets_connection() -> dict:
    if not settings.google_sheet_id:
        return {
            "configured": False,
            "connected": False,
            "credential_source": None,
            "message": "GOOGLE_SHEET_ID is not configured",
        }

    credential_source = (
        "GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT"
        if settings.google_service_account_json_content
        else "GOOGLE_SERVICE_ACCOUNT_JSON"
    )

    client = _get_client()
    sh = client.open_by_key(settings.google_sheet_id)
    return {
        "configured": True,
        "connected": True,
        "credential_source": credential_source,
        "spreadsheet_title": sh.title,
    }
