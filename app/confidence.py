"""
Confidence Score Layer
------------------------
Blends three signals per field:
  1. LLM self-reported confidence (from extraction.py)
  2. OCR-level confidence for tokens that literally appear in the OCR text
     (a value the LLM "typed" verbatim from high-confidence OCR text is more
     trustworthy than one it inferred)
  3. A format sanity check (dates parse, numbers are numeric, currency looks valid)

Overall invoice confidence weights financial fields higher, since those are
the fields where a silent error is most costly.
"""
import re
from datetime import datetime
from typing import Dict

FIELD_WEIGHTS = {
    "invoice_number": 1.0,
    "invoice_date": 1.0,
    "due_date": 0.6,
    "vendor_name": 1.0,
    "vendor_address": 0.5,
    "customer_name": 0.7,
    "customer_address": 0.4,
    "currency": 0.8,
    "subtotal": 1.3,
    "tax_amount": 1.1,
    "discount": 0.8,
    "total_amount": 1.5,
    "payment_terms": 0.4,
    "line_items": 1.2,
}

ISO_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


def _format_sanity_score(field: str, value) -> float:
    if value in (None, "", []):
        return 0.0
    try:
        if field in ("invoice_date", "due_date"):
            datetime.strptime(str(value), "%Y-%m-%d")
            return 1.0
        if field in ("subtotal", "tax_amount", "discount", "total_amount"):
            float(value)
            return 1.0
        if field == "currency":
            return 1.0 if ISO_CURRENCY_RE.match(str(value)) else 0.5
        return 1.0
    except (ValueError, TypeError):
        return 0.2


def _ocr_grounding_score(field: str, value, ocr_text: str) -> float:
    """Reward values that literally appear in the OCR text (cheap grounding check)."""
    if value in (None, "", []):
        return 0.5  # neutral, not zero -- missing fields are penalized elsewhere
    val_str = str(value).strip()
    if not val_str:
        return 0.5
    # For numeric fields compare loosely (strip trailing .0, commas)
    if field in ("subtotal", "tax_amount", "discount", "total_amount"):
        candidates = {val_str, val_str.rstrip("0").rstrip("."),
                      f"{float(val_str):,.2f}" if _is_number(val_str) else val_str}
        return 1.0 if any(c in ocr_text for c in candidates) else 0.6
    return 1.0 if val_str.lower() in ocr_text.lower() else 0.6


def _is_number(s) -> bool:
    try:
        float(s)
        return True
    except (ValueError, TypeError):
        return False


def compute_field_confidences(extracted: Dict, llm_confidences: Dict, ocr_text: str, ocr_avg_conf: float) -> Dict[str, float]:
    scores = {}
    for field, weight in FIELD_WEIGHTS.items():
        value = extracted.get(field)
        llm_conf = float(llm_confidences.get(field, 0.5))
        fmt_score = _format_sanity_score(field, value)
        grounding = _ocr_grounding_score(field, value, ocr_text)

        # Blend: LLM confidence carries the most weight, format + grounding sanity-check it,
        # and overall OCR quality sets a soft ceiling.
        blended = (0.5 * llm_conf) + (0.25 * fmt_score) + (0.25 * grounding)
        blended = min(blended, max(ocr_avg_conf, 0.4) + 0.15)  # OCR quality ceiling
        scores[field] = round(max(0.0, min(1.0, blended)), 3)
    return scores


def compute_overall_confidence(field_confidences: Dict[str, float]) -> float:
    total_weight = sum(FIELD_WEIGHTS.values())
    weighted_sum = sum(field_confidences.get(f, 0.0) * w for f, w in FIELD_WEIGHTS.items())
    return round(weighted_sum / total_weight, 3) if total_weight else 0.0


def low_confidence_fields(field_confidences: Dict[str, float], threshold: float) -> list[str]:
    return [f for f, score in field_confidences.items() if score < threshold]
