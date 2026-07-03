# Invoice OCR + Manual Review + Export System

An end-to-end, open-source invoice/bill/receipt processing pipeline:
**upload or email → pre-process → OCR + layout → LLM structured extraction →
confidence scoring → validation & duplicate detection → manual review UI →
export to Google Sheets / Excel / DB / CRM webhook.**

See `ARCHITECTURE.md` for the full design write-up (OCR engine comparison,
system diagram, API spec, Sheets column layout, validation rules).

## Stack (all free / open-source)

- **API**: FastAPI + SQLAlchemy (SQLite by default, swap to Postgres via `DATABASE_URL`)
- **Pre-processing**: OpenCV + PyMuPDF (deskew, denoise, CLAHE contrast, orientation, blur detection)
- **OCR**: PaddleOCR (PP-StructureV3) primary, RapidOCR fallback
- **Structured extraction**: Groq (`llama-3.3-70b-versatile`, free tier) — template-free JSON extraction with per-field confidence
- **Export**: gspread (Google Sheets, free service account) + openpyxl (Excel) + optional webhook for CRM/accounting (n8n/Zapier/Make)
- **Email ingestion**: IMAP via `imap-tools`
- **Review UI**: single-file vanilla HTML/JS (`static/review.html`) — no build step

## Quick start

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env: add GROQ_API_KEY, and (optionally) Google Sheets / IMAP credentials

uvicorn app.main:app --reload --port 8000
```

Open `http://localhost:8000/ui/review.html`, paste an `invoice_id` you get
back from the upload call, and start reviewing.

### Upload an invoice

```bash
curl -X POST http://localhost:8000/invoices/upload \
  -F "file=@/path/to/invoice.pdf"
```

Response includes `invoice_id`, extracted fields, per-field confidence,
overall confidence, and validation status.

### Review, correct, approve

```bash
# Get review payload
curl http://localhost:8000/invoices/{invoice_id}/review

# Correct fields
curl -X PATCH http://localhost:8000/invoices/{invoice_id}/fields \
  -H "Content-Type: application/json" \
  -d '{"field_updates": {"total_amount": 1250.00}, "changed_by": "tushar"}'

# Approve (triggers export to Sheets/webhook automatically)
curl -X POST http://localhost:8000/invoices/{invoice_id}/approve \
  -H "Content-Type: application/json" -d '{"reviewed_by": "tushar"}'
```

Approval is blocked while `validation_status == "flagged"` — fix the flagged
fields first (this is enforced server-side, not just in the UI).

### Export

- Every approval auto-exports to Google Sheets (if `GOOGLE_SHEET_ID` is set) and to the webhook (if `EXPORT_WEBHOOK_URL` is set).
- `GET /export/excel?status=approved` downloads a fresh `.xlsx` snapshot at any time.
- `POST /invoices/{id}/export` re-triggers export manually.

### Email ingestion

Set the `IMAP_*` values in `.env`, then either:
- call `POST /email/poll` on a schedule (cron, or an n8n Schedule Trigger → HTTP Request node, matching your existing n8n setup), or
- run `python -m app.email_ingest` directly as a standalone poller.

## Google Sheets setup (free)

1. Google Cloud Console → create a project → enable the **Google Sheets API**.
2. Create a **Service Account**, download its JSON key to `credentials/service_account.json`.
3. Open your target Google Sheet → Share → paste the service account's `client_email` with Editor access.
4. Put the sheet's ID (from its URL) into `GOOGLE_SHEET_ID` in `.env`.

No paid tier required — this uses the standard free Sheets API quota.

## Notes on scaling this up

- **GPU available later?** Swap `ocr_engine.py`'s primary call from PaddleOCR PP-StructureV3 to PaddleOCR-VL or Qwen2.5-VL — the rest of the pipeline (extraction/validation/review/export) is unaffected since it only depends on the `{full_text, tables, avg_confidence}` contract returned by `extract_text_and_layout()`.
- **Higher volume?** Move `run_pipeline()` off the request thread into a queue (Celery/RQ + Redis) and have `/invoices/upload` return immediately with a `processing` status; poll `/invoices/{id}` for completion.
- **Postgres**: just change `DATABASE_URL` — SQLAlchemy models don't need changes for a small-to-medium deployment.
- **CRM/accounting**: point `EXPORT_WEBHOOK_URL` at an n8n webhook and fan out to Zoho/HubSpot/QuickBooks/Xero from there, consistent with your existing n8n-based automations.

## Project layout

```
app/
  main.py            FastAPI routes
  config.py          env-driven settings
  database.py        SQLAlchemy models (Invoice, AuditLog)
  schemas.py         Pydantic request/response models
  preprocessing.py   PDF->image, deskew/denoise/contrast/orientation, blur scoring
  ocr_engine.py       PaddleOCR PP-StructureV3 + RapidOCR fallback
  extraction.py       Groq LLM structured JSON extraction
  confidence.py       per-field + overall confidence blending
  validation.py       required fields, formats, arithmetic cross-checks
  duplicate_check.py  exact + fuzzy duplicate detection
  pipeline.py         orchestrates the above end-to-end
  export_sheets.py    Google Sheets export
  export_excel.py     Excel export
  export_webhook.py   generic CRM/accounting webhook export
  email_ingest.py     IMAP polling -> pipeline
  audit.py            audit log writer
static/
  review.html         manual review UI (side-by-side original + editable fields)
```
