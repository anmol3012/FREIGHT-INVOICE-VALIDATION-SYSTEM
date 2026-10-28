from datetime import datetime, date
from sqlalchemy import Column, String, Float, Date, DateTime, ForeignKey, CheckConstraint, Enum as SAEnum
from sqlalchemy.orm import relationship
from backend.app.core.database import Base
from backend.app.models.enums import (
    CreditNoteApprovalStatus, CreditNoteReconciliationStatus
)

class CreditNote(Base):
    """
    Carrier credit note issued to settle disputed invoice exceptions.
    PK format: CN-2026-000001
    """
    __tablename__ = "credit_notes"

    credit_note_id = Column(String(40), primary_key=True, index=True)
    exception_id = Column(String(40), ForeignKey("audit_exceptions.exception_id", ondelete="SET NULL"), nullable=True, index=True)
    invoice_id = Column(String(40), ForeignKey("freight_invoices.invoice_id", ondelete="CASCADE"), nullable=False, index=True)
    carrier_id = Column(String(30), ForeignKey("carriers.carrier_id"), nullable=False, index=True)

    credit_note_number = Column(String(50), unique=True, index=True, nullable=False)
    issue_date = Column(Date, nullable=False, index=True)
    currency = Column(String(3), nullable=False, default="USD")
    credit_amount = Column(Float, nullable=False)

    approval_status = Column(SAEnum(CreditNoteApprovalStatus), nullable=False, default=CreditNoteApprovalStatus.PENDING_APPROVAL)
    reconciliation_status = Column(SAEnum(CreditNoteReconciliationStatus), nullable=False, default=CreditNoteReconciliationStatus.UNAPPLIED, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("credit_amount > 0", name="chk_credit_positive_amount"),
    )

    # Relationships
    audit_exception = relationship("AuditException", back_populates="credit_notes")
    invoice = relationship("FreightInvoice", back_populates="credit_notes")
    carrier = relationship("Carrier", back_populates="credit_notes")
