"""
Validation Layer
------------------
Structural + arithmetic sanity checks run before an invoice is allowed to be
approved. Produces a list of human-readable issues; the caller decides
severity (hard block vs. soft warning shown in the review UI).
"""
from datetime import datetime
from typing import Dict, List, Tuple

REQUIRED_FIELDS = ["invoice_number", "invoice_date", "vendor_name", "total_amount"]

VALID_CURRENCY_CODES = {
    "USD", "EUR", "GBP", "INR", "AUD", "CAD", "JPY", "CNY", "SGD", "AED",
    "CHF", "NZD", "ZAR", "BRL", "MXN", "HKD",
}


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(str(value), "%Y-%m-%d")
    except ValueError:
        return None


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def validate_invoice(extracted: Dict) -> Tuple[str, List[str]]:
    """
    Returns (status, notes) where status is 'passed' or 'flagged'.
    """
    issues: List[str] = []

    # 1. Required fields
    for field in REQUIRED_FIELDS:
        if not extracted.get(field):
            issues.append(f"Missing required field: {field}")

    # 2. Date validity
    inv_date = _parse_date(extracted.get("invoice_date"))
    due_date = _parse_date(extracted.get("due_date"))
    if extracted.get("invoice_date") and inv_date is None:
        issues.append("invoice_date is not a valid YYYY-MM-DD date")
    if extracted.get("due_date") and due_date is None:
        issues.append("due_date is not a valid YYYY-MM-DD date")
    if inv_date and due_date and due_date < inv_date:
        issues.append("due_date is earlier than invoice_date (warning)")

    # 3. Numeric validity
    subtotal = _to_float(extracted.get("subtotal"))
    tax = _to_float(extracted.get("tax_amount"))
    discount = _to_float(extracted.get("discount"))
    total = _to_float(extracted.get("total_amount"))

    for name, val in [("subtotal", extracted.get("subtotal")),
                       ("tax_amount", extracted.get("tax_amount")),
                       ("discount", extracted.get("discount")),
                       ("total_amount", extracted.get("total_amount"))]:
        if val not in (None, "") and _to_float(val) is None:
            issues.append(f"{name} is not numeric: {val!r}")
        elif _to_float(val) is not None and _to_float(val) < 0:
            issues.append(f"{name} is negative: {val}")

    # 4. Currency validity
    currency = extracted.get("currency")
    if currency and currency.upper() not in VALID_CURRENCY_CODES:
        issues.append(f"Unrecognized currency code: {currency}")

    # 5. Arithmetic cross-check: subtotal + tax - discount ≈ total
    if None not in (subtotal, tax, total):
        discount_val = discount or 0.0
        expected_total = subtotal + tax - discount_val
        tolerance = max(0.01, 0.005 * (total or 0))
        if abs(expected_total - total) > tolerance:
            issues.append(
                f"Total mismatch: subtotal({subtotal}) + tax({tax}) - discount({discount_val}) "
                f"= {expected_total:.2f}, but total_amount = {total:.2f}"
            )

    # 6. Line item math
    line_items = extracted.get("line_items") or []
    line_total_sum = 0.0
    for idx, item in enumerate(line_items):
        qty = _to_float(item.get("quantity"))
        price = _to_float(item.get("unit_price"))
        line_total = _to_float(item.get("line_total"))
        if None not in (qty, price, line_total):
            expected = qty * price
            tolerance = max(0.01, 0.005 * (line_total or 0))
            if abs(expected - line_total) > tolerance:
                issues.append(
                    f"Line item {idx + 1} math mismatch: {qty} x {price} = {expected:.2f}, "
                    f"but line_total = {line_total:.2f}"
                )
        if line_total is not None:
            line_total_sum += line_total

    if line_items and subtotal is not None and line_total_sum:
        tolerance = max(0.02, 0.01 * subtotal)
        if abs(line_total_sum - subtotal) > tolerance:
            issues.append(
                f"Sum of line items ({line_total_sum:.2f}) does not match subtotal ({subtotal:.2f})"
            )

    status = "passed" if not issues else "flagged"
    return status, issues
