"""
Export Layer - Google Sheets
----------------------------
Uses a Google service account via gspread.
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

FLAT_HEADERS = [
    "Invoice Number",
    "Vendor Name",
    "Customer Name",
    "Invoice Date",
    "Due Date",
    "Currency",
    "Subtotal",
    "Tax Amount",
    "Total Amount",
    "Status",
]
LEGACY_FLAT_HEADERS = ["vendor_name", "customer_name", "subtotal", "tax_amount", "total_amount", "status"]
LINE_ITEM_HEADERS = ["Invoice Number", "Description", "Quantity", "Unit Price", "Line Total"]


def _load_service_account_info(raw_content: str, source_name: str) -> dict:
    try:
        content = raw_content.strip()
        if content.startswith("'") and content.endswith("'"):
            content = content[1:-1]
        return json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"{source_name} is set but is not valid JSON. "
            "In Railway, paste the full service account JSON object as the variable value. "
            f"Details: {e}"
        ) from e


def _get_client():
    if settings.google_service_account_json_content:
        info = _load_service_account_info(
            settings.google_service_account_json_content,
            "GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT",
        )
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
        return gspread.authorize(creds)

    creds_path = settings.google_service_account_json
    if creds_path.strip().startswith("{"):
        info = _load_service_account_info(creds_path, "GOOGLE_SERVICE_ACCOUNT_JSON")
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
        return gspread.authorize(creds)

    if not os.path.exists(creds_path):
        raise FileNotFoundError(
            f"Service account credentials not found. "
            f"For local dev: place the JSON at '{creds_path}'. "
            f"For Railway/cloud: set GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT to the full "
            f"contents of the service account JSON file, or paste the full JSON into "
            f"GOOGLE_SERVICE_ACCOUNT_JSON instead of using a local file path."
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
    try:
        existing = ws.row_values(1)
    except Exception:
        existing = []

    if not existing or not any(v.strip() for v in existing):
        ws.insert_row(headers, index=1)


def _normalized_headers(headers: list[str]) -> list[str]:
    return [h.strip().lower().replace(" ", "_") for h in headers]


def _first_empty_row(ws: gspread.Worksheet) -> int:
    values = ws.get_all_values()
    for idx, row in enumerate(values):
        if idx == 0:
            continue
        if not row or not any(cell.strip() for cell in row):
            return idx + 1
    return len(values) + 1


def _safe(val) -> str:
    if val is None:
        return ""
    return str(val)


def export_invoice_to_sheets(invoice: Invoice, file_url: str = ""):
    client = _get_client()
    sh = client.open_by_key(settings.google_sheet_id)

    ws = _get_or_create_worksheet(sh, "Invoices", FLAT_HEADERS)
    _ensure_headers(ws, FLAT_HEADERS)

    existing_headers = _normalized_headers(ws.row_values(1))
    legacy_headers = _normalized_headers(LEGACY_FLAT_HEADERS)
    status = invoice.status.replace("_", " ").title() if invoice.status else ""
    next_row = _first_empty_row(ws)

    if existing_headers[:len(legacy_headers)] == legacy_headers:
        row = [
            _safe(invoice.vendor_name),
            _safe(invoice.customer_name),
            _safe(invoice.subtotal),
            _safe(invoice.tax_amount),
            _safe(invoice.total_amount),
            status,
        ]
        ws.update(range_name=f"A{next_row}:F{next_row}", values=[row], value_input_option="USER_ENTERED")
    else:
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
            status,
        ]
        ws.update(range_name=f"A{next_row}:J{next_row}", values=[row], value_input_option="USER_ENTERED")

    logger.info("Exported invoice %s to Google Sheets 'Invoices' tab row %s", invoice.id, next_row)

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
    try:
        invoices_ws = sh.worksheet("Invoices")
        invoices_headers = invoices_ws.row_values(1)
        invoices_rows = len(invoices_ws.get_all_values())
    except gspread.WorksheetNotFound:
        invoices_headers = []
        invoices_rows = 0

    return {
        "configured": True,
        "connected": True,
        "credential_source": credential_source,
        "spreadsheet_title": sh.title,
        "worksheets": [ws.title for ws in sh.worksheets()],
        "invoices_headers": invoices_headers,
        "invoices_row_count": invoices_rows,
    }
