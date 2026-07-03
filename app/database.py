import datetime
import uuid

from sqlalchemy import (Boolean, Column, DateTime, Float, ForeignKey,
                         Integer, String, Text, create_engine)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from app.config import settings

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def gen_id() -> str:
    return str(uuid.uuid4())


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(String, primary_key=True, default=gen_id)
    original_filename = Column(String)
    file_path = Column(String)
    file_hash = Column(String, nullable=True, index=True)
    source = Column(String, default="upload")  # upload | email
    email_sender = Column(String, nullable=True)
    email_subject = Column(String, nullable=True)

    # Extracted fields (post-review values live here; raw OCR/LLM output kept in extraction table)
    invoice_number = Column(String, nullable=True)
    invoice_date = Column(String, nullable=True)
    due_date = Column(String, nullable=True)
    vendor_name = Column(String, nullable=True)
    vendor_address = Column(Text, nullable=True)
    customer_name = Column(String, nullable=True)
    customer_address = Column(Text, nullable=True)
    currency = Column(String, nullable=True)
    subtotal = Column(Float, nullable=True)
    tax_amount = Column(Float, nullable=True)
    discount = Column(Float, nullable=True)
    total_amount = Column(Float, nullable=True)
    payment_terms = Column(String, nullable=True)
    line_items_json = Column(Text, nullable=True)  # JSON string

    overall_confidence = Column(Float, nullable=True)
    field_confidence_json = Column(Text, nullable=True)  # JSON string: {field: score}
    validation_status = Column(String, default="pending")  # passed | flagged | pending
    validation_notes = Column(Text, nullable=True)
    validation_ai_suggestions = Column(Text, nullable=True)
    invoice_summary = Column(Text, nullable=True)  # LLM-generated one-line description

    is_duplicate = Column(Boolean, default=False)
    duplicate_of = Column(String, nullable=True)

    status = Column(String, default="pending_review")  # pending_review | approved | rejected
    reviewed_by = Column(String, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    audit_logs = relationship("AuditLog", back_populates="invoice", cascade="all, delete-orphan")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    invoice_id = Column(String, ForeignKey("invoices.id"))
    field_name = Column(String)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    changed_by = Column(String, nullable=True)
    changed_at = Column(DateTime, default=datetime.datetime.utcnow)
    action = Column(String, default="edit")  # edit | approve | reject | export

    invoice = relationship("Invoice", back_populates="audit_logs")


class GoogleOAuthToken(Base):
    __tablename__ = "google_oauth_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text, nullable=True)
    token_uri = Column(Text, nullable=False)
    client_id = Column(Text, nullable=False)
    client_secret = Column(Text, nullable=False)
    scopes = Column(Text, nullable=False)
    expiry = Column(DateTime, nullable=False)
    email = Column(String, nullable=True)



def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
