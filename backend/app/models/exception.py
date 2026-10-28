from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from backend.app.core.database import Base

class InvoiceException(Base):
    __tablename__ = "invoice_exceptions"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True)
    invoice_line_id = Column(Integer, ForeignKey("invoice_lines.id", ondelete="SET NULL"), nullable=True, index=True)
    
    # Negative scenario category:
    # BASE_RATE_MISMATCH, WEIGHT_DISCREPANCY, UNAUTHORIZED_ACCESSORIAL, DUPLICATE_BILLING, INVALID_CREDIT_NOTE, CALCULATION_ERROR
    category = Column(String(50), nullable=False, index=True)
    severity = Column(String(20), default="CRITICAL") # INFO, WARNING, CRITICAL
    
    billed_amount = Column(Float, nullable=False, default=0.0)
    expected_amount = Column(Float, nullable=False, default=0.0)
    variance_amount = Column(Float, nullable=False, default=0.0)
    
    # Workflow status: OPEN, UNDER_REVIEW, APPROVED_OVERRIDE, DISPUTED, AUTO_RESOLVED
    status = Column(String(30), default="OPEN", index=True)
    root_cause_code = Column(String(50), nullable=False) # e.g. TARIFF_RATE_INFLATION, SCALE_WEIGHT_EXCEEDED, NO_POD_PROOF, DUPLICATE_INVOICE_HASH
    explanation = Column(Text, nullable=False)
    
    resolved_by = Column(String(50), nullable=True) # e.g. SYSTEM, AUDITOR, ADMIN
    resolution_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)

    # Relationships
    invoice = relationship("InvoiceHeader", back_populates="exceptions")
    invoice_line = relationship("InvoiceLine", back_populates="exceptions")
