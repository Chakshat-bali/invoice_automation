import json
import os
import shutil
import logging
import hashlib
from datetime import datetime

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, BackgroundTasks
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.audit import log_change
from app.config import settings
from app.database import Invoice, GoogleOAuthToken, gen_id, get_db, init_db
from app.export_excel import export_invoices_to_excel
from app.export_sheets import export_invoice_to_sheets
from app.export_webhook import export_invoice_to_webhook
from app.pipeline import run_pipeline
from app.schemas import ApproveRequest, FieldUpdateRequest
from app.validation import validate_invoice

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Invoice OCR + Review + Export System")

# Allow all origins for Vercel deployment
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()

from fastapi.responses import HTMLResponse

frontend_dist = os.path.join("frontend", "dist")
if os.path.isdir(frontend_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist, "assets")), name="assets")
    
    @app.get("/")
    @app.get("/review/{id}")
    def serve_react_app(id: str = None):
        with open(os.path.join(frontend_dist, "index.html"), "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())

    @app.get("/ui/{full_path:path}")
    def redirect_legacy_ui(full_path: str):
        # Redirect old /ui/review.html?id=xyz to /review/xyz, or just /
        return RedirectResponse(url="/")

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".bmp"}


def _invoice_dir(invoice_id: str) -> str:
    d = os.path.join(settings.storage_dir, invoice_id)
    os.makedirs(d, exist_ok=True)
    return d


def _serialize_invoice(inv: Invoice) -> dict:
    return {
        "invoice_id": inv.id,
        "original_filename": inv.original_filename,
        "source": inv.source,
        "email_sender": inv.email_sender,
        "email_subject": inv.email_subject,
        "invoice_number": inv.invoice_number,
        "invoice_date": inv.invoice_date,
        "due_date": inv.due_date,
        "vendor_name": inv.vendor_name,
        "vendor_address": inv.vendor_address,
        "customer_name": inv.customer_name,
        "customer_address": inv.customer_address,
        "currency": inv.currency,
        "subtotal": inv.subtotal,
        "tax_amount": inv.tax_amount,
        "discount": inv.discount,
        "total_amount": inv.total_amount,
        "payment_terms": inv.payment_terms,
        "line_items": json.loads(inv.line_items_json) if inv.line_items_json else [],
        "overall_confidence": inv.overall_confidence,
        "field_confidence": json.loads(inv.field_confidence_json) if inv.field_confidence_json else {},
        "validation_status": inv.validation_status,
        "validation_notes": inv.validation_notes,
        "validation_ai_suggestions": inv.validation_ai_suggestions,
        "is_duplicate": inv.is_duplicate,
        "duplicate_of": inv.duplicate_of,
        "status": inv.status,
        "reviewed_by": inv.reviewed_by,
        "reviewed_at": inv.reviewed_at.isoformat() if inv.reviewed_at else None,
        "created_at": inv.created_at.isoformat() if inv.created_at else None,
        "file_url": f"/invoices/{inv.id}/file",
    }


def process_invoice_background(invoice_id: str, file_path: str, inv_dir: str):
    logger.info(f"Starting background processing for invoice {invoice_id}")
    # Get a fresh DB session for the background task
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        result = run_pipeline(file_path, os.path.join(inv_dir, "work"), db)
        extracted = result["extracted"]
        logger.info(f"Extraction complete for {invoice_id}. Validation status: {result['validation_status']}")
        if result['validation_notes']:
            logger.warning(f"Validation notes for {invoice_id}: {result['validation_notes']}")

        invoice = db.get(Invoice, invoice_id)
        if not invoice:
            logger.error(f"Invoice {invoice_id} not found in background task")
            return

        invoice.invoice_number = extracted.get("invoice_number")
        invoice.invoice_date = extracted.get("invoice_date")
        invoice.due_date = extracted.get("due_date")
        invoice.vendor_name = extracted.get("vendor_name")
        invoice.vendor_address = extracted.get("vendor_address")
        invoice.customer_name = extracted.get("customer_name")
        invoice.customer_address = extracted.get("customer_address")
        invoice.currency = extracted.get("currency")
        invoice.subtotal = extracted.get("subtotal")
        invoice.tax_amount = extracted.get("tax_amount")
        invoice.discount = extracted.get("discount")
        invoice.total_amount = extracted.get("total_amount")
        invoice.payment_terms = extracted.get("payment_terms")
        invoice.line_items_json = json.dumps(extracted.get("line_items", []))
        invoice.invoice_summary = extracted.get("invoice_summary")
        invoice.overall_confidence = result["overall_confidence"]
        invoice.field_confidence_json = json.dumps(result["field_confidence"])
        invoice.validation_status = result["validation_status"]
        invoice.validation_notes = result["validation_notes"]
        invoice.validation_ai_suggestions = result.get("validation_ai_suggestions")
        invoice.is_duplicate = result["is_duplicate"]
        invoice.duplicate_of = result["duplicate_of"]
        invoice.status = "pending_review"

        db.commit()
        logger.info(f"Background processing complete for ID: {invoice_id}")
    except Exception as e:
        logger.error(f"Error in background processing for {invoice_id}: {e}")
        invoice = db.get(Invoice, invoice_id)
        if invoice:
            invoice.status = "error"
            invoice.validation_notes = str(e)
            db.commit()
    finally:
        db.close()


@app.post("/invoices/upload")
async def upload_invoice(file: UploadFile = File(...),
                          background_tasks: BackgroundTasks = None,
                          email_sender: str | None = None,
                          email_subject: str | None = None,
                          db: Session = Depends(get_db)):
    logger.info(f"Received upload request for file: {file.filename}")
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        logger.error(f"Unsupported file type: {ext}")
        raise HTTPException(400, f"Unsupported file type: {ext}")

    # Compute hash to check for duplicates
    file_bytes = await file.read()
    file_hash = hashlib.sha256(file_bytes).hexdigest()
    
    # Check if hash already exists in DB
    existing = db.query(Invoice).filter(Invoice.file_hash == file_hash, Invoice.status != "error").first()
    if existing:
        logger.warning(f"Duplicate file upload attempt: {file.filename} matches invoice {existing.id}")
        raise HTTPException(400, f"This exact file has already been uploaded.")

    invoice_id = gen_id()
    inv_dir = _invoice_dir(invoice_id)
    saved_path = os.path.join(inv_dir, f"original{ext}")
    with open(saved_path, "wb") as f:
        f.write(file_bytes)
    logger.info(f"Saved file to: {saved_path}")

    # Create initial record
    invoice = Invoice(
        id=invoice_id,
        original_filename=file.filename,
        file_path=saved_path,
        file_hash=file_hash,
        source="email" if email_sender else "upload",
        email_sender=email_sender,
        email_subject=email_subject,
        status="processing",
    )
    db.add(invoice)
    log_change(db, invoice_id, "*", None, "created via upload (processing)", changed_by="system", action="create")
    db.commit()
    logger.info(f"Initial invoice record created with ID: {invoice_id}")

    if background_tasks:
        background_tasks.add_task(process_invoice_background, invoice_id, saved_path, inv_dir)

    return _serialize_invoice(invoice)


@app.get("/invoices")
def list_invoices(status: str | None = None, vendor: str | None = None, db: Session = Depends(get_db)):
    query = db.query(Invoice).filter(Invoice.status != "error")
    if status:
        query = query.filter(Invoice.status == status)
    if vendor:
        query = query.filter(Invoice.vendor_name.ilike(f"%{vendor}%"))
    invoices = query.order_by(Invoice.created_at.desc()).all()
    return [_serialize_invoice(i) for i in invoices]


@app.get("/invoices/{invoice_id}")
def get_invoice(invoice_id: str, db: Session = Depends(get_db)):
    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(404, "Invoice not found")
    return _serialize_invoice(inv)


@app.get("/invoices/{invoice_id}/review")
def get_invoice_for_review(invoice_id: str, db: Session = Depends(get_db)):
    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(404, "Invoice not found")
    data = _serialize_invoice(inv)
    threshold = settings.low_confidence_threshold
    data["low_confidence_fields"] = [
        f for f, score in data["field_confidence"].items() if score < threshold
    ]
    return data


@app.get("/invoices/{invoice_id}/file")
def get_invoice_file(invoice_id: str, db: Session = Depends(get_db)):
    inv = db.get(Invoice, invoice_id)
    if not inv or not os.path.exists(inv.file_path):
        raise HTTPException(404, "File not found")
    return FileResponse(inv.file_path, filename=inv.original_filename)





@app.patch("/invoices/{invoice_id}/fields")
def update_fields(invoice_id: str, req: FieldUpdateRequest, db: Session = Depends(get_db)):
    logger.info(f"Received update fields request for invoice ID: {invoice_id}")
    logger.info(f"Field updates requested: {req.field_updates}")
    
    inv = db.get(Invoice, invoice_id)
    if not inv:
        logger.error(f"Invoice not found with ID: {invoice_id}")
        raise HTTPException(404, "Invoice not found")

    editable = {"invoice_number", "invoice_date", "due_date", "vendor_name", "vendor_address",
                "customer_name", "customer_address", "currency", "subtotal", "tax_amount",
                "discount", "total_amount", "payment_terms", "line_items", "original_filename"}

    for field, new_value in req.field_updates.items():
        if field not in editable:
            logger.warning(f"Skipping non-editable field: {field}")
            continue
        old_value = getattr(inv, "line_items_json" if field == "line_items" else field)
        if field == "line_items":
            new_stored = json.dumps(new_value)
            setattr(inv, "line_items_json", new_stored)
        else:
            setattr(inv, field, new_value)
            new_stored = new_value
        logger.info(f"Updating field '{field}': old='{old_value}' new='{new_value}'")
        log_change(db, invoice_id, field, old_value, new_stored, changed_by=req.changed_by, action="edit")

    # Re-run validation against corrected data
    extracted_for_validation = {
        "invoice_number": inv.invoice_number, "invoice_date": inv.invoice_date,
        "vendor_name": inv.vendor_name, "total_amount": inv.total_amount,
        "due_date": inv.due_date, "subtotal": inv.subtotal, "tax_amount": inv.tax_amount,
        "discount": inv.discount, "currency": inv.currency,
        "line_items": json.loads(inv.line_items_json) if inv.line_items_json else [],
    }
    status, notes = validate_invoice(extracted_for_validation)
    logger.info(f"Re-validation status: {status}")
    if notes:
        logger.warning(f"Validation notes: {notes}")
        # Try to fetch a new AI suggestion since it's still flagged
        from app.resolution import generate_resolution_suggestion
        inv.validation_ai_suggestions = generate_resolution_suggestion(extracted_for_validation, notes)
    else:
        inv.validation_ai_suggestions = None
    
    inv.validation_status = status
    inv.validation_notes = "; ".join(notes) if notes else None
    inv.updated_at = datetime.utcnow()

    db.commit()
    logger.info(f"Successfully updated invoice ID: {invoice_id}")
    return _serialize_invoice(inv)


@app.post("/invoices/{invoice_id}/approve")
def approve_invoice(invoice_id: str, req: ApproveRequest, db: Session = Depends(get_db)):
    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(404, "Invoice not found")
    if inv.validation_status == "flagged":
        error_msg = "Cannot approve a flagged invoice. Resolve validation issues first: " + (inv.validation_notes or "")
        if inv.validation_ai_suggestions:
            error_msg += f" \n\n🤖 AI Suggestion: {inv.validation_ai_suggestions}"
        raise HTTPException(400, error_msg)

    inv.status = "approved"
    inv.reviewed_by = req.reviewed_by
    inv.reviewed_at = datetime.utcnow()
    log_change(db, invoice_id, "status", "pending_review", "approved", changed_by=req.reviewed_by, action="approve")
    db.commit()

    export_results = _run_exports(inv)
    return {"invoice": _serialize_invoice(inv), "export_results": export_results}


@app.post("/invoices/{invoice_id}/reject")
def reject_invoice(invoice_id: str, req: ApproveRequest, db: Session = Depends(get_db)):
    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(404, "Invoice not found")
    inv.status = "rejected"
    inv.reviewed_by = req.reviewed_by
    inv.reviewed_at = datetime.utcnow()
    log_change(db, invoice_id, "status", "pending_review", "rejected", changed_by=req.reviewed_by, action="reject")
    db.commit()
    return _serialize_invoice(inv)


@app.get("/invoices/{invoice_id}/audit-log")
def get_audit_log(invoice_id: str, db: Session = Depends(get_db)):
    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(404, "Invoice not found")
    return [
        {
            "field_name": log.field_name, "old_value": log.old_value, "new_value": log.new_value,
            "changed_by": log.changed_by, "changed_at": log.changed_at.isoformat(), "action": log.action,
        }
        for log in sorted(inv.audit_logs, key=lambda l: l.changed_at)
    ]


def _run_exports(inv: Invoice) -> dict:
    results = {"sheets": None, "webhook": None}
    file_url = f"/invoices/{inv.id}/file"
    try:
        if settings.google_sheet_id:
            export_invoice_to_sheets(inv, file_url)
            results["sheets"] = "success"
    except Exception as e:  # noqa: BLE001
        results["sheets"] = f"error: {e}"

    try:
        if settings.export_webhook_url:
            export_invoice_to_webhook(inv)
            results["webhook"] = "success"
    except Exception as e:  # noqa: BLE001
        results["webhook"] = f"error: {e}"

    return results


@app.post("/invoices/{invoice_id}/export")
def manual_export(invoice_id: str, db: Session = Depends(get_db)):
    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(404, "Invoice not found")
    results = _run_exports(inv)
    log_change(db, invoice_id, "*", None, json.dumps(results), changed_by="system", action="export")
    db.commit()
    return results


@app.get("/export/excel")
def export_excel(status: str | None = None, db: Session = Depends(get_db)):
    query = db.query(Invoice)
    if status:
        query = query.filter(Invoice.status == status)
    else:
        query = query.filter(Invoice.status != "error")
    ids = [i.id for i in query.all()]
    out_path = export_invoices_to_excel(db, ids)
    return FileResponse(out_path, filename=os.path.basename(out_path))
@app.get("/export/sheets/link")
def get_sheets_link():
    if not settings.google_sheet_id:
        return {"url": None}
    return {"url": f"https://docs.google.com/spreadsheets/d/{settings.google_sheet_id}"}



@app.delete("/invoices/{invoice_id}")
def delete_invoice(invoice_id: str, db: Session = Depends(get_db)):
    logger.info(f"Received delete request for invoice ID: {invoice_id}")
    inv = db.get(Invoice, invoice_id)
    if not inv:
        logger.error(f"Invoice not found with ID: {invoice_id}")
        raise HTTPException(404, "Invoice not found")

    # Delete files
    inv_dir = os.path.join(settings.storage_dir, invoice_id)
    if os.path.exists(inv_dir):
        logger.info(f"Deleting invoice directory: {inv_dir}")
        shutil.rmtree(inv_dir)

    # Delete from database
    db.delete(inv)
    db.commit()
    logger.info(f"Successfully deleted invoice ID: {invoice_id}")
    return {"status": "success", "invoice_id": invoice_id}


@app.post("/email/poll")
def trigger_email_poll(db: Session = Depends(get_db)):
    from app.email_ingest import poll_inbox
    processed = poll_inbox(db)
    return {"processed": processed}


SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid"
]


@app.get("/auth/google/url")
def get_google_auth_url():
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(400, "Google Client ID or Client Secret not configured in .env")
    
    from google_auth_oauthlib.flow import Flow
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=SCOPES,
        redirect_uri="http://localhost:8000/auth/google/callback"
    )
    auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
    return {"url": auth_url}


@app.get("/auth/google/callback")
def google_auth_callback(code: str, db: Session = Depends(get_db)):
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(400, "Google OAuth not configured")

    from google_auth_oauthlib.flow import Flow
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=SCOPES,
        redirect_uri="http://localhost:8000/auth/google/callback"
    )
    flow.fetch_token(code=code)
    creds = flow.credentials

    # Query connected email
    from googleapiclient.discovery import build
    service = build("oauth2", "v2", credentials=creds)
    user_info = service.userinfo().get().execute()
    email = user_info.get("email")

    db.query(GoogleOAuthToken).delete()
    
    token_entry = GoogleOAuthToken(
        access_token=creds.token,
        refresh_token=creds.refresh_token,
        token_uri=creds.token_uri,
        client_id=creds.client_id,
        client_secret=creds.client_secret,
        scopes=",".join(creds.scopes),
        expiry=creds.expiry,
        email=email
    )
    db.add(token_entry)
    db.commit()

    return RedirectResponse(url="/?connected=google")


@app.get("/auth/google/status")
def google_auth_status(db: Session = Depends(get_db)):
    token = db.query(GoogleOAuthToken).first()
    if not token:
        return {"connected": False, "email": None}
    return {"connected": True, "email": token.email}


@app.post("/auth/google/disconnect")
def google_auth_disconnect(db: Session = Depends(get_db)):
    db.query(GoogleOAuthToken).delete()
    db.commit()
    return {"status": "success"}


@app.get("/health")
def health():
    return {"status": "ok"}
