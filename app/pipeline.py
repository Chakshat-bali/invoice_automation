import json
import os

from sqlalchemy.orm import Session

from app.config import settings
from app.confidence import compute_field_confidences, compute_overall_confidence
from app.duplicate_check import find_duplicate
from app.extraction import extract_structured_data, extract_data_via_vision
from app.ocr_engine import extract_text_and_layout, merge_pages
from app.preprocessing import preprocess_file, is_native_pdf, extract_native_pdf_text
from app.validation import validate_invoice
from app.resolution import generate_resolution_suggestion


def run_pipeline(file_path: str, work_dir: str, db: Session):
    """
    Runs the full pre-process -> OCR -> extract -> confidence -> validate ->
    duplicate-check pipeline. Returns a dict ready to persist on an Invoice row.
    """
    # 1. Native PDF Fast-Path check
    if settings.bypass_native_pdf_ocr and is_native_pdf(file_path):
        extracted_text, page_count = extract_native_pdf_text(file_path)
        ocr_merged = {
            "full_text": extracted_text,
            "avg_confidence": 1.0,
            "blocks": [],
            "tables": [],
            "page_count": page_count,
        }
        table_html_blocks = []
        page_results = [
            {
                "page_number": i + 1,
                "cleaned_path": None,
                "blur_score": 999.0,
                "is_blurry": False,
                "skew_angle_corrected": 0.0,
                "resolution": "digital",
                "quality_flag": "ok",
            } for i in range(page_count)
        ]
        # Structured extraction via LLM
        extracted = extract_structured_data(ocr_merged["full_text"], table_html_blocks)
        is_invoice = extracted.pop("is_invoice", True)
        if not is_invoice:
            raise ValueError("Please upload a valid invoice file")
        llm_confidences = extracted.pop("field_confidence", {})
    else:
        # We need to render/preprocess PDF pages to images for either Vision API or Local OCR
        page_results = preprocess_file(file_path, work_dir)
        
        # Check if we should attempt Multimodal Vision Extraction
        use_vision = settings.use_vision_extraction
        if use_vision:
            provider = settings.vision_provider.lower()
            if provider == "gemini" and not settings.gemini_api_key:
                # If Gemini key is missing, check if Groq key is present to redirect
                if not settings.groq_api_key:
                    use_vision = False
            elif provider == "groq" and not settings.groq_api_key:
                use_vision = False

        extracted = None
        llm_confidences = {}
        ocr_merged = None

        if use_vision:
            try:
                # 2. Vision Path: Extract data directly from the rendered images
                img_paths = [p["cleaned_path"] for p in page_results]
                extracted = extract_data_via_vision(img_paths)
                is_invoice = extracted.pop("is_invoice", True)
                if not is_invoice:
                    raise ValueError("Please upload a valid invoice file")
                llm_confidences = extracted.pop("field_confidence", {})
                
                # Mock ocr_merged metadata since we bypassed CPU OCR
                ocr_merged = {
                    "full_text": "",
                    "avg_confidence": 0.95,
                    "blocks": [],
                    "tables": [],
                    "page_count": len(page_results),
                }
            except Exception as e:
                # Fallback to local OCR path on failure (e.g. rate limit, offline)
                import logging
                logger = logging.getLogger("uvicorn.error")
                logger.error(f"Multimodal Vision extraction failed, falling back to local OCR. Error: {e}")
                use_vision = False

        if not use_vision:
            # 3. Local OCR Fallback (Phase 3)
            ocr_page_results = [extract_text_and_layout(p["cleaned_path"]) for p in page_results]
            ocr_merged = merge_pages(ocr_page_results)
            table_html_blocks = [t.get("html", "") for t in ocr_merged.get("tables", []) if t.get("html")]
            
            # Structured extraction via LLM
            extracted = extract_structured_data(ocr_merged["full_text"], table_html_blocks)
            is_invoice = extracted.pop("is_invoice", True)
            if not is_invoice:
                raise ValueError("Please upload a valid invoice file")
            llm_confidences = extracted.pop("field_confidence", {})

    # 5. Confidence scoring
    field_confidences = compute_field_confidences(
        extracted, llm_confidences, ocr_merged["full_text"], ocr_merged["avg_confidence"]
    )
    overall_confidence = compute_overall_confidence(field_confidences)

    # 6. Validation
    validation_status, validation_notes = validate_invoice(extracted)

    # 6b. Duplicate detection
    is_duplicate, duplicate_of = find_duplicate(db, extracted)
    if is_duplicate:
        validation_status = "flagged"
        validation_notes.append(f"Possible duplicate of invoice {duplicate_of}")

    # 7. AI Validation Assistant
    validation_ai_suggestions = None
    if validation_status == "flagged" and validation_notes:
        validation_ai_suggestions = generate_resolution_suggestion(extracted, validation_notes)

    return {
        "extracted": extracted,
        "field_confidence": field_confidences,
        "overall_confidence": overall_confidence,
        "validation_status": validation_status,
        "validation_notes": "; ".join(validation_notes) if validation_notes else None,
        "validation_ai_suggestions": validation_ai_suggestions,
        "is_duplicate": is_duplicate,
        "duplicate_of": duplicate_of,
        "ocr_quality": {
            "avg_confidence": ocr_merged["avg_confidence"],
            "page_count": ocr_merged["page_count"],
            "pages": page_results,
        },
    }
