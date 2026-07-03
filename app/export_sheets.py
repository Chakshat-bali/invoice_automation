"""
Export Layer — Google Sheets
------------------------------
Uses a free Google service account (no paid API tier required) via gspread.
Setup: create a service account in Google Cloud Console, enable the Sheets
API, download the JSON key to `credentials/service_account.json`, and share
your target Google Sheet with the service account's email address.
"""
import json
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials

from app.config import settings
from app.database import Invoice

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

FLAT_HEADERS = [
    "vendor_name", "customer_name", "subtotal", "tax_amount", 
    "total_amount", "status"
]

LINE_ITEM_HEADERS = ["invoice_id", "description", "quantity", "unit_price", "line_total"]


def _get_client():
    creds = Credentials.from_service_account_file(settings.google_service_account_json, scopes=SCOPES)
    return gspread.authorize(creds)


def _get_or_create_worksheet(sh, title: str, headers: list[str]):
    try:
        ws = sh.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=title, rows=1000, cols=len(headers) + 2)
        ws.append_row(headers)
    return ws


def export_invoice_to_sheets(invoice: Invoice, file_url: str = ""):
    client = _get_client()
    sh = client.open_by_key(settings.google_sheet_id)

    ws = _get_or_create_worksheet(sh, "Invoices", FLAT_HEADERS)
    
    # We enforce writing the correct headers to row 1 to fix mismatched columns
    # from previous exports if the sheet already existed.
    ws.update('A1:F1', [FLAT_HEADERS])

    row = [
        invoice.vendor_name, 
        invoice.customer_name, 
        invoice.subtotal, 
        invoice.tax_amount,
        invoice.total_amount, 
        invoice.status
    ]
    
    # Find the first empty row in the sheet to prevent appending at the very bottom (e.g. row 1001)
    values = ws.get_all_values()
    next_row = len(values) + 1
    for idx, r in enumerate(values):
        if idx == 0:
            continue
        if not r or not any(cell.strip() for cell in r):
            next_row = idx + 1
            break

    ws.update(f'A{next_row}:F{next_row}', [row], value_input_option="USER_ENTERED")

    if settings.sheets_mode == "normalized" and invoice.line_items_json:
        items_ws = _get_or_create_worksheet(sh, "Line Items", LINE_ITEM_HEADERS)
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
            items_ws.update(f'A{curr_row}:E{curr_row}', [[
                invoice.id, item.get("description"), item.get("quantity"),
                item.get("unit_price"), item.get("line_total"),
            ]], value_input_option="USER_ENTERED")

    return True
