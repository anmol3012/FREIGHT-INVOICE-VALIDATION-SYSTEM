from datetime import datetime, date
from sqlalchemy import Column, Integer, String, Float, Date, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from backend.app.core.database import Base

class CreditNote(Base):
    __tablename__ = "credit_notes"

    id = Column(Integer, primary_key=True, index=True)
    credit_note_number = Column(String(50), unique=True, index=True, nullable=False)
    carrier_id = Column(Integer, ForeignKey("carriers.id"), nullable=False, index=True)
    original_invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False, index=True)
    issue_date = Column(Date, nullable=False)
    credit_amount = Column(Float, nullable=False)
    applied_amount = Column(Float, default=0.0)
    remaining_balance = Column(Float, nullable=False)
    
    # Status: UNAPPLIED, PARTIALLY_APPLIED, FULLY_APPLIED, REJECTED
    status = Column(String(30), default="UNAPPLIED", index=True)
    reason_code = Column(String(50), nullable=False) # RATE_CORRECTION, WEIGHT_ADJUSTMENT, ACCESSORIAL_REFUND
    rejection_reason = Column(Text, nullable=True) # E.g. "Amount exceeds original invoice dispute balance"
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    carrier = relationship("Carrier", back_populates="credit_notes")
    original_invoice = relationship("InvoiceHeader", back_populates="credit_notes")
