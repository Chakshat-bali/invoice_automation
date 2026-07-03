# AI Invoice OCR + Review + Export System — Architecture

## 1. OCR engine research summary (as of mid-2026)

| Engine | Type | Strengths | Weaknesses | Verdict |
|---|---|---|---|---|
| **PaddleOCR (PP-OCRv5 + PP-StructureV3)** | Classic detector+recognizer, Apache-2.0 | Built-in table/layout analysis (line items!), CPU-friendly, 80+ languages, actively developed, `PaddleOCR-VL-1.5` adds VLM-grade layout understanding | PaddlePaddle framework is unfamiliar to most Python devs; English docs thinner | **Primary OCR engine** |
| RapidOCR | ONNX port of PaddleOCR models | Lightest footprint (50–80MB), fastest raw text speed, no framework dependency, great for containers | No PP-Structure table recognition | Fallback / fast-path for text-only docs |
| Tesseract 5.x | Classic LSTM | Extremely well known, ~10MB, decent accuracy on clean scans | Weak on multi-column/table layouts, needs manual page-segmentation tuning | Fallback for degraded/simple scans |
| EasyOCR | Classic, PyTorch | Handles handwriting/mixed scripts okay | ~3x slower, ~500MB models | Not primary; optional handwriting fallback |
| Groq (llama-3.3-70b-versatile) / Gemini | LLM structured extraction | Turns messy OCR text into structured JSON with reasoning about which line is "total" vs "subtotal"; free-tier friendly on Groq | Not an OCR engine itself — needs OCR text or vision input first | **Extraction layer**, not OCR layer |

**Recommendation for this build:** PaddleOCR (PP-StructureV3) as the primary OCR + layout/table engine, running self-hosted, CPU-only compatible (matches your NCERT pipeline server constraint). RapidOCR as a lightweight fallback for text-only invoices where PP-Structure is unnecessary. Groq's `llama-3.3-70b-versatile` (already in use in your recruitment n8n workflow) turns OCR output into structured JSON fields with self-reported confidence — this mirrors the MinerU + Gemini fallback pattern from the NCERT project. Everything is free/open-source; only the Groq API call uses a free-tier hosted LLM, which you're already using elsewhere.

Why not a pure OCR-free VLM (Qwen2.5-VL, GOT-OCR2.0, PaddleOCR-VL)? They give higher raw accuracy on messy layouts, but they need a GPU for real-time throughput. Since your existing infra is CPU-only, PaddleOCR PP-StructureV3 + an LLM extraction pass gets ~90% of the benefit without a GPU. If a GPU becomes available later, swapping in PaddleOCR-VL or Qwen2.5-VL is a drop-in replacement for the OCR layer only — the rest of the pipeline (extraction/validation/review/export) doesn't change.

## 2. System architecture

```
┌────────────────┐      ┌──────────────────┐      ┌───────────────────┐
│ Input Layer     │      │ Pre-processing    │      │ OCR + Layout Layer │
│ - Web upload    │─────▶│ - PDF→image (pdf2 │─────▶│ - PaddleOCR         │
│ - Email (IMAP)  │      │   image / PyMuPDF)│      │   PP-StructureV3    │
│ - Store original│      │ - deskew/denoise  │      │ - table + KV boxes  │
└────────────────┘      │ - contrast/orient  │      └─────────┬──────────┘
                          └──────────────────┘                 │
                                                                 ▼
┌────────────────┐      ┌──────────────────┐      ┌───────────────────┐
│ Export Layer    │      │ Manual Review     │      │ Extraction Layer   │
│ - Google Sheets │◀─────│ - editable form    │◀─────│ - Groq LLM JSON     │
│ - Excel (.xlsx) │      │ - side-by-side PDF │      │   structured fields │
│ - SQLite DB     │      │ - approve/reject   │      │ - field confidence  │
│ - CRM/Zapier    │      └────────┬──────────┘      └─────────┬──────────┘
│   webhook (opt) │               │                             │
└────────────────┘                ▼                             ▼
                          ┌──────────────────┐      ┌───────────────────┐
                          │ Validation Layer   │◀─────│ Confidence Layer    │
                          │ - required fields   │      │ - per-field score   │
                          │ - math cross-check   │      │ - overall score      │
                          │ - duplicate check    │      │ - low-conf flags     │
                          └──────────────────┘      └───────────────────┘
```

All layers run in a single FastAPI service (`app/main.py`) backed by SQLite (swap for Postgres later by changing `DATABASE_URL`). Audit log table records every manual edit (old value → new value, who, when).

## 3. Step-by-step workflow

1. **Ingest** — File dropped via `POST /invoices/upload`, or `email_ingest.py` polls an IMAP inbox every N minutes, pulls PDF/image attachments, and calls the same upload pipeline internally. Original file is saved untouched to `storage/uploads/{invoice_id}/original.*`.
2. **Pre-process** — `preprocessing.py` converts PDF pages to images (PyMuPDF), then runs OpenCV: grayscale, denoise, deskew (Hough-based angle detection), adaptive contrast (CLAHE), and orientation correction (0/90/180/270 via OSD heuristic). Blur/resolution is scored (Laplacian variance) and flagged if below threshold.
3. **OCR + layout** — `ocr_engine.py` runs PaddleOCR PP-StructureV3 on the cleaned image, returning text blocks with bounding boxes plus detected tables (candidate line items) and per-token recognition confidence.
4. **Structured extraction** — `extraction.py` sends the OCR text (+ table blocks) to Groq with a strict JSON schema prompt covering every required field. The LLM also returns a self-assessed 0–1 confidence per field, which is blended with the OCR recognition confidence for tokens that were matched verbatim.
5. **Confidence scoring** — `confidence.py` computes: field confidence = weighted blend of (a) OCR token confidence for matched text, (b) LLM self-reported confidence, (c) a regex/format sanity check (e.g. does "invoice_date" parse as a date). Overall invoice confidence = weighted average, weighted more heavily toward financial fields (total, tax, subtotal).
6. **Validation** — `validation.py` checks: required fields present, date formats valid, numeric fields are numeric, currency is a recognized ISO code/symbol, and `subtotal + tax - discount ≈ total` (within rounding tolerance). `duplicate_check.py` flags invoices matching an existing (vendor, invoice_number, total) or (vendor, date, total) combination already in the DB.
7. **Manual review** — `GET /invoices/{id}/review` returns the extracted JSON + confidence + validation flags + a URL to the original file. `static/review.html` is a lightweight side-by-side viewer (PDF/image on the left, editable form on the right, low-confidence fields highlighted in amber, failed validations in red).
8. **Approve/reject** — `PATCH /invoices/{id}/fields` saves corrections and writes an audit-log row per changed field. `POST /invoices/{id}/approve` or `/reject` finalizes status.
9. **Export** — On approval, `export_sheets.py` appends a row to Google Sheets via a service account (free, no paid tier needed), `export_excel.py` can generate a `.xlsx` snapshot on demand, and everything is always persisted in SQLite regardless of downstream export. An optional generic `webhook_export()` POSTs the final JSON to any CRM/accounting webhook URL (Zapier/Make/n8n — which slots straight into your existing n8n habit).

## 4. Google Sheets column structure

| Column | Field | Notes |
|---|---|---|
| A | invoice_id | internal UUID |
| B | invoice_number | |
| C | invoice_date | ISO `YYYY-MM-DD` |
| D | due_date | ISO `YYYY-MM-DD` |
| E | vendor_name | |
| F | vendor_address | |
| G | customer_name | |
| H | customer_address | |
| I | currency | ISO 4217 code |
| J | subtotal | numeric |
| K | tax_amount | numeric |
| L | discount | numeric |
| M | total_amount | numeric |
| N | payment_terms | free text |
| O | line_items_json | JSON array: `[{description, qty, unit_price, line_total}]` |
| P | overall_confidence | 0–1 |
| Q | validation_status | `passed` / `flagged` |
| R | validation_notes | e.g. "total mismatch by 0.02" |
| S | email_sender | if received via email |
| T | email_subject | if received via email |
| U | reviewed_by | user id/email |
| V | reviewed_at | timestamp |
| W | original_file_url | link to stored file |
| X | status | `pending_review` / `approved` / `rejected` |

Line items are kept as a JSON blob in one column for simplicity; a second optional sheet tab (`Line Items`) can be written with one row per line item (invoice_id, description, qty, unit_price, line_total) if you want normalized reporting — `export_sheets.py` supports both (`SHEETS_MODE=flat|normalized` in `.env`).

## 5. API design

| Method | Path | Purpose |
|---|---|---|
| POST | `/invoices/upload` | multipart upload (PDF/JPG/PNG) → runs pre-processing + OCR + extraction, returns `invoice_id` + extracted data + confidence |
| GET | `/invoices/{id}` | fetch stored invoice (raw + extracted + status) |
| GET | `/invoices/{id}/review` | data shaped for the review UI (fields, confidence, validation flags, file URL) |
| PATCH | `/invoices/{id}/fields` | body: `{field_updates: {field: value, ...}}` → applies corrections, writes audit log |
| POST | `/invoices/{id}/approve` | marks approved, triggers export |
| POST | `/invoices/{id}/reject` | marks rejected, no export |
| GET | `/invoices` | list/filter by status, vendor, date range |
| GET | `/invoices/{id}/audit-log` | full change history |
| POST | `/invoices/{id}/export` | manually (re)trigger export to sheets/excel/webhook |
| GET | `/invoices/{id}/file` | serve the original stored file |
| POST | `/email/poll` | manually trigger one IMAP poll cycle (also runnable as a cron/n8n schedule) |

## 6. Validation rules implemented

- **Required fields**: `invoice_number`, `invoice_date`, `vendor_name`, `total_amount` must be non-empty.
- **Date validity**: `invoice_date`/`due_date` must parse to a real calendar date; `due_date >= invoice_date` (warning, not hard fail).
- **Numeric validity**: `subtotal`, `tax_amount`, `discount`, `total_amount`, and each line item's `quantity`/`unit_price` must be parseable numbers ≥ 0.
- **Currency validity**: must match a known ISO 4217 code or recognized symbol; if only a symbol is found, it's mapped to a code where unambiguous.
- **Arithmetic cross-check**: `abs((subtotal + tax_amount - discount) - total_amount) <= tolerance` (tolerance = greater of 0.01 or 0.5% of total, to absorb rounding).
- **Line item math**: for each line item, `quantity * unit_price ≈ line_total` (same tolerance rule); sum of line totals compared to subtotal.
- **Duplicate detection**: exact match on `(vendor_name, invoice_number)`, or fuzzy match on `(vendor_name, invoice_date, total_amount)` within existing approved/pending invoices.
- **Confidence gating**: any field below `LOW_CONFIDENCE_THRESHOLD` (default 0.75) is flagged for mandatory human review before approval is allowed.
