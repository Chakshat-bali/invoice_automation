from sqlalchemy.orm import Session

from app.database import AuditLog


def log_change(db: Session, invoice_id: str, field_name: str, old_value, new_value,
                changed_by: str = "system", action: str = "edit"):
    entry = AuditLog(
        invoice_id=invoice_id,
        field_name=field_name,
        old_value=str(old_value) if old_value is not None else None,
        new_value=str(new_value) if new_value is not None else None,
        changed_by=changed_by,
        action=action,
    )
    db.add(entry)
