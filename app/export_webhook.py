"""
Optional Export — CRM / Accounting webhook
---------------------------------------------
Posts the final, approved invoice JSON to any webhook URL (n8n, Zapier, Make,
or a native CRM/accounting API endpoint). This keeps the core system
decoupled from any specific CRM vendor -- point EXPORT_WEBHOOK_URL at an n8n
webhook node and route to Zoho/HubSpot/QuickBooks/Xero from there, matching
your existing n8n-based automation style.
"""
import json

import requests

from app.config import settings
from app.database import Invoice


def export_invoice_to_webhook(invoice: Invoice) -> bool:
    if not settings.export_webhook_url:
        return False

    payload = {
        "invoice_id": invoice.id,
        "invoice_number": invoice.invoice_number,
        "invoice_date": invoice.invoice_date,
        "due_date": invoice.due_date,
        "vendor_name": invoice.vendor_name,
        "vendor_address": invoice.vendor_address,
        "customer_name": invoice.customer_name,
        "customer_address": invoice.customer_address,
        "currency": invoice.currency,
        "subtotal": invoice.subtotal,
        "tax_amount": invoice.tax_amount,
        "discount": invoice.discount,
        "total_amount": invoice.total_amount,
        "payment_terms": invoice.payment_terms,
        "line_items": json.loads(invoice.line_items_json) if invoice.line_items_json else [],
        "status": invoice.status,
        "reviewed_by": invoice.reviewed_by,
    }
    resp = requests.post(settings.export_webhook_url, json=payload, timeout=15)
    resp.raise_for_status()
    return True
