from datetime import datetime
from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Text, Enum as SAEnum
from sqlalchemy.orm import relationship
from backend.app.core.database import Base
from backend.app.models.enums import (
    ExceptionType, ExceptionSeverity, ExceptionStatus
)

class AuditException(Base):
    """
    Actionable audit exception ticket tracking billing discrepancies and contractual variances.
    PK format: FEX-2026-000001
    """
    __tablename__ = "audit_exceptions"

    exception_id = Column(String(40), primary_key=True, index=True)
    invoice_id = Column(String(40), ForeignKey("freight_invoices.invoice_id", ondelete="CASCADE"), nullable=False, index=True)
    invoice_line_id = Column(String(50), ForeignKey("invoice_lines.invoice_line_id", ondelete="SET NULL"), nullable=True, index=True)
    shipment_id = Column(String(30), ForeignKey("shipments.shipment_id", ondelete="SET NULL"), nullable=True, index=True)

    exception_type = Column(SAEnum(ExceptionType), nullable=False, index=True)
    severity = Column(SAEnum(ExceptionSeverity), nullable=False, default=ExceptionSeverity.CRITICAL)

    expected_amount = Column(Float, nullable=False, default=0.0)
    billed_amount = Column(Float, nullable=False, default=0.0)
    disputed_amount = Column(Float, nullable=False, default=0.0) # billed - expected
    currency = Column(String(3), nullable=False, default="USD")

    explanation = Column(Text, nullable=False)
    evidence_json = Column(Text, nullable=True) # JSON snapshot of rate card, scale readings, and POD proof

    exception_status = Column(SAEnum(ExceptionStatus), nullable=False, default=ExceptionStatus.OPEN, index=True)
    detected_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    resolved_at = Column(DateTime, nullable=True)

    # Relationships
    invoice = relationship("FreightInvoice", back_populates="audit_exceptions")
    invoice_line = relationship("InvoiceLine", back_populates="audit_exceptions")
    shipment = relationship("Shipment", back_populates="audit_exceptions")
    credit_notes = relationship("CreditNote", back_populates="audit_exception")
