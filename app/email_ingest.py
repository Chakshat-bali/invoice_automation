"""
Input Layer — Gmail ingestion via Google API
--------------------------------
Polls a Gmail inbox using OAuth credentials stored in the DB, downloads unread
attachments, and processes them through the OCR extraction pipeline.
"""
import os
import base64
import json
import hashlib
import logging
from datetime import datetime

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Invoice, GoogleOAuthToken, gen_id
from app.pipeline import run_pipeline

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".bmp"}


def get_gmail_credentials(db: Session, session_id: str = "default"):
    token_entry = db.query(GoogleOAuthToken).filter(GoogleOAuthToken.session_id == session_id).first()
    if not token_entry:
        return None
        
    creds = Credentials(
        token=token_entry.access_token,
        refresh_token=token_entry.refresh_token,
        token_uri=token_entry.token_uri,
        client_id=token_entry.client_id,
        client_secret=token_entry.client_secret,
        scopes=token_entry.scopes.split(",")
    )
    
    # Check if creds need refresh
    if creds.expired or (token_entry.expiry and datetime.utcnow() >= token_entry.expiry):
        try:
            creds.refresh(Request())
            # Save updated values back to DB
            token_entry.access_token = creds.token
            if creds.expiry:
                token_entry.expiry = creds.expiry
            db.commit()
        except Exception as e:
            print(f"Error refreshing token: {e}")
            return None
            
    return creds


def poll_inbox(db: Session, session_id: str = "default") -> list[str]:
    creds = get_gmail_credentials(db, session_id)
    if not creds:
        print("Google OAuth is not connected or credentials expired.")
        return []
        
    processed_ids = []
    try:
        service = build("gmail", "v1", credentials=creds)
        # Search unread messages
        results = service.users().messages().list(userId="me", q="is:unread").execute()
        messages = results.get("messages", [])
        
        for msg_summary in messages:
            msg_id = msg_summary["id"]
            msg = service.users().messages().get(userId="me", id=msg_id).execute()
            
            # Extract headers (subject, sender)
            headers = msg.get("payload", {}).get("headers", [])
            subject = "No Subject"
            sender = "Unknown Sender"
            for h in headers:
                if h["name"].lower() == "subject":
                    subject = h["value"]
                elif h["name"].lower() == "from":
                    sender = h["value"]
            
            # Extract attachments
            parts = msg.get("payload", {}).get("parts", [])
            attachments_to_process = []
            
            def walk_parts(parts_list):
                for part in parts_list:
                    filename = part.get("filename")
                    body = part.get("body", {})
                    attachment_id = body.get("attachmentId")
                    if filename and attachment_id:
                        ext = os.path.splitext(filename)[1].lower()
                        if ext in ALLOWED_EXTENSIONS:
                            attachments_to_process.append((filename, attachment_id, ext))
                    if "parts" in part:
                        walk_parts(part["parts"])
            
            walk_parts(parts)
            
            for filename, att_id, ext in attachments_to_process:
                # Fetch full attachment data
                attachment = service.users().messages().attachments().get(
                    userId="me", messageId=msg_id, id=att_id
                ).execute()
                
                data = attachment.get("data")
                if not data:
                    continue
                
                file_bytes = base64.urlsafe_b64decode(data.encode("UTF-8"))
                
                # Compute hash to avoid processing same exact file twice
                file_hash = hashlib.sha256(file_bytes).hexdigest()
                existing = db.query(Invoice).filter(Invoice.file_hash == file_hash, Invoice.status != "error").first()
                if existing:
                    logger.info(f"Skipping duplicate attachment {filename} (matches invoice {existing.id})")
                    continue
                
                invoice_id = gen_id()
                inv_dir = os.path.join(settings.storage_dir, invoice_id)
                os.makedirs(inv_dir, exist_ok=True)
                saved_path = os.path.join(inv_dir, f"original{ext}")
                with open(saved_path, "wb") as f:
                    f.write(file_bytes)
                
                # Run pipeline
                result = run_pipeline(saved_path, os.path.join(inv_dir, "work"), db)
                extracted = result["extracted"]
                
                invoice = Invoice(
                    id=invoice_id,
                    session_id=session_id,
                    original_filename=filename,
                    file_path=saved_path,
                    file_hash=file_hash,
                    source="email",
                    email_sender=sender,
                    email_subject=subject,
                    invoice_number=extracted.get("invoice_number"),
                    invoice_date=extracted.get("invoice_date"),
                    due_date=extracted.get("due_date"),
                    vendor_name=extracted.get("vendor_name"),
                    vendor_address=extracted.get("vendor_address"),
                    customer_name=extracted.get("customer_name"),
                    customer_address=extracted.get("customer_address"),
                    currency=extracted.get("currency"),
                    subtotal=extracted.get("subtotal"),
                    tax_amount=extracted.get("tax_amount"),
                    discount=extracted.get("discount"),
                    total_amount=extracted.get("total_amount"),
                    payment_terms=extracted.get("payment_terms"),
                    line_items_json=json.dumps(extracted.get("line_items", [])),
                    overall_confidence=result["overall_confidence"],
                    field_confidence_json=json.dumps(result["field_confidence"]),
                    validation_status=result["validation_status"],
                    validation_notes=result["validation_notes"],
                    is_duplicate=result["is_duplicate"],
                    duplicate_of=result["duplicate_of"],
                    status="pending_review",
                )
                db.add(invoice)
                db.commit()
                processed_ids.append(invoice_id)
            
            # Mark message as read
            service.users().messages().batchModify(
                userId="me",
                body={"ids": [msg_id], "removeLabelIds": ["UNREAD"]}
            ).execute()
                
    except Exception as e:
        print(f"Error querying Gmail API: {e}")
        
    return processed_ids


if __name__ == "__main__":
    from app.database import SessionLocal, init_db
    init_db()
    session = SessionLocal()
    ids = poll_inbox(session)
    print(f"Processed {len(ids)} invoice(s) from email: {ids}")
    session.close()
