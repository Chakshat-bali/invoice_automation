"""
Export Layer — Google Sheets
------------------------------
Uses a free Google service account (no paid API tier required) via gspread.
Setup: create a service account in Google Cloud Console, enable the Sheets
API, download the JSON key to `credentials/service_account.json`, and share
your target Google Sheet with the service account's email address.
"""
import json
import os

import gspread
from google.oauth2.service_account import Credentials

from app.config import settings
from app.database import Invoice

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

FLAT_HEADERS = ["Vendor Name", "Customer Name", "Subtotal", "Tax Amount", "Total Amount", "Status"]

LINE_ITEM_HEADERS = ["Invoice Number", "Description", "Quantity", "Unit Price", "Line Total"]


def _get_client():
    creds_path = settings.google_service_account_json
    if not os.path.exists(creds_path):
        raise FileNotFoundError(
            f"Service account JSON not found at '{creds_path}'. "
            f"Please ensure credentials/service_account.json exists or set GOOGLE_SERVICE_ACCOUNT_JSON in .env"
        )
    creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
    return gspread.authorize(creds)


def _get_or_create_worksheet(sh, title: str, headers: list[str]):
    try:
        ws = sh.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=title, rows=1000, cols=len(headers) + 2)
    return ws


def _safe(val) -> str:
    """Convert None / floats to plain strings so gspread never drops a cell."""
    if val is None:
        return ""
    return str(val)


def export_invoice_to_sheets(invoice: Invoice, file_url: str = ""):
    client = _get_client()
    sh = client.open_by_key(settings.google_sheet_id)

    ws = _get_or_create_worksheet(sh, "Invoices", FLAT_HEADERS)

    # Always write headers to row 1 so the sheet is self-describing
    ws.update(range_name='A1:F1', values=[FLAT_HEADERS])

    row = [
        _safe(invoice.vendor_name),
        _safe(invoice.customer_name),
        _safe(invoice.subtotal),
        _safe(invoice.tax_amount),
        _safe(invoice.total_amount),
        invoice.status.replace("_", " ").title() if invoice.status else "",
    ]

    # Find first truly empty data row (skip header at index 0)
    values = ws.get_all_values()
    next_row = len(values) + 1
    for idx, r in enumerate(values):
        if idx == 0:
            continue
        if not r or not any(cell.strip() for cell in r):
            next_row = idx + 1
            break

    ws.update(range_name=f'A{next_row}:F{next_row}', values=[row])

    if settings.sheets_mode == "normalized" and invoice.line_items_json:
        items_ws = _get_or_create_worksheet(sh, "Line Items", LINE_ITEM_HEADERS)
        items_ws.update(range_name='A1:E1', values=[LINE_ITEM_HEADERS])
        try:
            items = json.loads(invoice.line_items_json)
        except json.JSONDecodeError:
            items = []

        items_values = items_ws.get_all_values()
        items_next_row = len(items_values) + 1
        for idx, r in enumerate(items_values):
            if idx == 0:
                continue
            if not r or not any(cell.strip() for cell in r):
                items_next_row = idx + 1
                break

        for i, item in enumerate(items):
            curr_row = items_next_row + i
            items_ws.update(range_name=f'A{curr_row}:E{curr_row}', values=[[
                _safe(invoice.invoice_number),
                _safe(item.get("description")),
                _safe(item.get("quantity")),
                _safe(item.get("unit_price")),
                _safe(item.get("line_total")),
            ]])

    return True
