"""
Data Extraction Layer
-----------------------
Turns raw OCR text + detected tables into structured invoice fields using
Groq's hosted LLM (free tier). This is template-free: it works across
arbitrary vendor layouts because the model reasons over the text rather than
relying on fixed coordinates.

The prompt forces strict JSON output including a confidence score (0-1) per
field, which the confidence layer later blends with OCR-level token confidence.
"""
import base64
import json
import os
import re
from typing import Dict

import httpx
from groq import Groq

from app.config import settings

SYSTEM_PROMPT = """You are an expert invoice data extraction engine. You will be given raw OCR
text extracted from an invoice, receipt, or bill (layout may be imperfect due to OCR noise).

Extract the following fields and return ONLY valid JSON, no markdown, no commentary:

{
  "is_invoice": boolean,
  "invoice_number": string or null,
  "invoice_date": string (YYYY-MM-DD) or null,
  "due_date": string (YYYY-MM-DD) or null,
  "vendor_name": string or null,
  "vendor_address": string or null,
  "customer_name": string or null,
  "customer_address": string or null,
  "currency": string (ISO 4217 code, e.g. USD/INR/EUR) or null,
  "subtotal": number or null,
  "tax_amount": number or null,
  "discount": number or null,
  "total_amount": number or null,
  "payment_terms": string or null,
  "line_items": [
    {"description": string, "quantity": number, "unit_price": number, "line_total": number}
  ],
  "invoice_summary": string or null,
  "field_confidence": {
    "invoice_number": number (0-1),
    "invoice_date": number (0-1),
    "due_date": number (0-1),
    "vendor_name": number (0-1),
    "vendor_address": number (0-1),
    "customer_name": number (0-1),
    "customer_address": number (0-1),
    "currency": number (0-1),
    "subtotal": number (0-1),
    "tax_amount": number (0-1),
    "discount": number (0-1),
    "total_amount": number (0-1),
    "payment_terms": number (0-1),
    "line_items": number (0-1)
  }
}

- Set is_invoice to true if the text clearly represents an invoice, receipt, bill, or purchase order. Set is_invoice to false if the text represents any other document (e.g. general articles, personal letters, tax returns, resumes, blank images, etc.).
- If a field is not present in the text, set it to null and give it a confidence of 0.
- Normalize all dates to YYYY-MM-DD if the original format is unambiguous; otherwise keep your best guess and lower confidence.
- Normalize numbers by stripping currency symbols/commas.
- confidence should reflect how certain you are the OCR text unambiguously supports that value (1.0 = explicit and clear, 0.5 = inferred/ambiguous, 0.0 = missing).
- Never invent values that aren't grounded in the text.
- invoice_summary must be a single sentence (max 20 words) describing what this invoice is for, e.g. "Web development and UI/UX services from TechSolutions to ABC Corp for INR 87,966."
"""


def _extract_json_block(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return match.group(0) if match else text


def extract_structured_data(ocr_text: str, table_html_blocks: list[str] | None = None) -> Dict:
    """
    Calls Groq to turn OCR text (+ optional table HTML from PP-Structure) into
    structured invoice fields with per-field confidence.
    """
    # Create our own httpx client to avoid SDK version issues with 'proxies'
    http_client = httpx.Client(
        timeout=60.0,
        follow_redirects=True
    )
    client = Groq(
        api_key=settings.groq_api_key,
        http_client=http_client
    )

    user_content = f"OCR TEXT:\n{ocr_text}\n"
    if table_html_blocks:
        user_content += "\nDETECTED TABLES (HTML, likely line items):\n"
        user_content += "\n---\n".join(table_html_blocks)

    response = client.chat.completions.create(
        model=settings.groq_model,
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
    )

    raw = response.choices[0].message.content
    json_str = _extract_json_block(raw)

    try:
        parsed = json.loads(json_str)
    except json.JSONDecodeError:
        # Retry once with a repair pass asking the model to fix its own JSON
        repair = client.chat.completions.create(
            model=settings.groq_model,
            temperature=0,
            messages=[
                {"role": "system", "content": "Fix this into strictly valid JSON. Return ONLY the JSON."},
                {"role": "user", "content": raw},
            ],
        )
        parsed = json.loads(_extract_json_block(repair.choices[0].message.content))

    parsed.setdefault("line_items", [])
    parsed.setdefault("field_confidence", {})
    return parsed


VISION_SYSTEM_PROMPT = """You are an expert invoice data extraction engine. You will be given one or more page images of an invoice, receipt, or bill.

Extract the following fields and return ONLY valid JSON, no markdown, no commentary:

{
  "is_invoice": boolean,
  "invoice_number": string or null,
  "invoice_date": string (YYYY-MM-DD) or null,
  "due_date": string (YYYY-MM-DD) or null,
  "vendor_name": string or null,
  "vendor_address": string or null,
  "customer_name": string or null,
  "customer_address": string or null,
  "currency": string (ISO 4217 code, e.g. USD/INR/EUR) or null,
  "subtotal": number or null,
  "tax_amount": number or null,
  "discount": number or null,
  "total_amount": number or null,
  "payment_terms": string or null,
  "line_items": [
    {"description": string, "quantity": number, "unit_price": number, "line_total": number}
  ],
  "invoice_summary": string or null,
  "field_confidence": {
    "invoice_number": number (0-1),
    "invoice_date": number (0-1),
    "due_date": number (0-1),
    "vendor_name": number (0-1),
    "vendor_address": number (0-1),
    "customer_name": number (0-1),
    "customer_address": number (0-1),
    "currency": number (0-1),
    "subtotal": number (0-1),
    "tax_amount": number (0-1),
    "discount": number (0-1),
    "total_amount": number (0-1),
    "payment_terms": number (0-1),
    "line_items": number (0-1)
  }
}

- Set is_invoice to true if the document represents an invoice, receipt, bill, or purchase order. Set is_invoice to false otherwise.
- If a field is not present in the document, set it to null and give it a confidence of 0.
- Normalize all dates to YYYY-MM-DD if the original format is unambiguous; otherwise keep your best guess and lower confidence.
- Normalize numbers by stripping currency symbols/commas.
- confidence should reflect how certain you are the visual data supports that value (1.0 = explicit and clear, 0.5 = inferred/ambiguous, 0.0 = missing).
- Never invent values that aren't grounded in the visual document.
- invoice_summary must be a single sentence (max 20 words) describing what this invoice is for, e.g. "Web development and UI/UX services from TechSolutions to ABC Corp for INR 87,966."
"""


def extract_data_via_vision(image_paths: list[str]) -> Dict:
    """
    Calls the configured multimodal vision model (Gemini or Groq) to extract
    structured invoice data directly from invoice page images.
    """
    if not image_paths:
        raise ValueError("No images provided for vision extraction")

    provider = settings.vision_provider.lower()
    
    # Fallback to groq if gemini key is missing but groq key is present
    if provider == "gemini" and not settings.gemini_api_key:
        if settings.groq_api_key:
            import logging
            logger = logging.getLogger("uvicorn.error")
            logger.warning("Gemini key is missing. Automatically redirecting to Groq vision provider.")
            provider = "groq"
        else:
            raise ValueError("GEMINI_API_KEY is not configured in .env")

    if provider == "gemini":
        return _extract_via_gemini_vision(image_paths)
    elif provider == "groq":
        if not settings.groq_api_key:
            raise ValueError("GROQ_API_KEY is not configured in .env")
        return _extract_via_groq_vision(image_paths)
    else:
        raise ValueError(f"Unsupported vision provider: {provider}")


def _extract_via_gemini_vision(image_paths: list[str]) -> Dict:
    model = settings.vision_model
    if "gemini" not in model.lower():
        model = "gemini-1.5-flash"  # fallback default
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={settings.gemini_api_key}"
    
    parts = [{"text": VISION_SYSTEM_PROMPT}]
    for path in image_paths:
        ext = os.path.splitext(path)[1].lower()
        mime_type = "image/png" if ext == ".png" else "image/jpeg"
        with open(path, "rb") as f:
            img_data = base64.b64encode(f.read()).decode("utf-8")
        parts.append({
            "inlineData": {
                "mimeType": mime_type,
                "data": img_data
            }
        })
        
    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0
        }
    }
    
    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        response = client.post(url, json=payload)
        response.raise_for_status()
        result = response.json()
        
    try:
        raw_text = result["candidates"][0]["content"]["parts"][0]["text"]
        json_str = _extract_json_block(raw_text)
        parsed = json.loads(json_str)
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        raise ValueError(f"Gemini API returned an invalid response structure or invalid JSON: {e}")
        
    parsed.setdefault("line_items", [])
    parsed.setdefault("field_confidence", {})
    return parsed


def _extract_via_groq_vision(image_paths: list[str]) -> Dict:
    model = settings.vision_model
    if "llama" not in model.lower() and "scout" not in model.lower():
        model = "meta-llama/llama-4-scout-17b-16e-instruct"  # fallback default

    content = [{"type": "text", "text": VISION_SYSTEM_PROMPT}]
    
    for path in image_paths:
        ext = os.path.splitext(path)[1].lower()
        mime_type = "image/png" if ext == ".png" else "image/jpeg"
        with open(path, "rb") as f:
            img_data = base64.b64encode(f.read()).decode("utf-8")
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:{mime_type};base64,{img_data}"
            }
        })
        
    http_client = httpx.Client(timeout=60.0, follow_redirects=True)
    client = Groq(api_key=settings.groq_api_key, http_client=http_client)
    
    response = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {"role": "user", "content": content}
        ]
    )
    
    raw = response.choices[0].message.content
    json_str = _extract_json_block(raw)
    
    try:
        parsed = json.loads(json_str)
    except json.JSONDecodeError:
        repair = client.chat.completions.create(
            model=settings.groq_model,
            temperature=0,
            messages=[
                {"role": "system", "content": "Fix this into strictly valid JSON. Return ONLY the JSON."},
                {"role": "user", "content": raw},
            ],
        )
        parsed = json.loads(_extract_json_block(repair.choices[0].message.content))
        
    parsed.setdefault("line_items", [])
    parsed.setdefault("field_confidence", {})
    return parsed
