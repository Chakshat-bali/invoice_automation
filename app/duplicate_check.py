"""
Duplicate detection: exact match on (vendor, invoice_number), or fuzzy match
on (vendor, invoice_date, total_amount) against existing invoices that aren't
rejected.
"""
from typing import Optional, Tuple

from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from app.database import Invoice

FUZZY_VENDOR_THRESHOLD = 90


def find_duplicate(db: Session, extracted: dict, exclude_id: Optional[str] = None) -> Tuple[bool, Optional[str]]:
    vendor = (extracted.get("vendor_name") or "").strip()
    invoice_number = (extracted.get("invoice_number") or "").strip()
    invoice_date = extracted.get("invoice_date")
    total = extracted.get("total_amount")

    query = db.query(Invoice).filter(Invoice.status != "rejected")
    if exclude_id:
        query = query.filter(Invoice.id != exclude_id)
    candidates = query.all()

    for c in candidates:
        c_vendor = (c.vendor_name or "").strip()
        vendor_match = (
            vendor and c_vendor and
            (vendor.lower() == c_vendor.lower() or fuzz.ratio(vendor.lower(), c_vendor.lower()) >= FUZZY_VENDOR_THRESHOLD)
        )
        if not vendor_match:
            continue

        # Exact match: same vendor + same invoice number
        if invoice_number and c.invoice_number and invoice_number.lower() == c.invoice_number.lower():
            return True, c.id

        # Fuzzy match: same vendor + same date + same total
        if invoice_date and c.invoice_date and total is not None and c.total_amount is not None:
            if invoice_date == c.invoice_date and abs(float(total) - float(c.total_amount)) < 0.01:
                return True, c.id

    return False, None
