from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class LineItem(BaseModel):
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    line_total: Optional[float] = None


class ExtractedInvoice(BaseModel):
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    vendor_name: Optional[str] = None
    vendor_address: Optional[str] = None
    customer_name: Optional[str] = None
    customer_address: Optional[str] = None
    currency: Optional[str] = None
    subtotal: Optional[float] = None
    tax_amount: Optional[float] = None
    discount: Optional[float] = None
    total_amount: Optional[float] = None
    payment_terms: Optional[str] = None
    line_items: List[LineItem] = []


class FieldUpdateRequest(BaseModel):
    field_updates: Dict[str, Any]
    changed_by: Optional[str] = "reviewer"


class ApproveRequest(BaseModel):
    reviewed_by: Optional[str] = "reviewer"


class UploadResponse(BaseModel):
    invoice_id: str
    extracted: ExtractedInvoice
    field_confidence: Dict[str, float]
    overall_confidence: float
    validation_status: str
    validation_notes: Optional[str] = None
    is_duplicate: bool = False
