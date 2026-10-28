from datetime import datetime, date
from sqlalchemy import Column, Integer, String, Float, Boolean, Date, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from backend.app.core.database import Base

class InvoiceHeader(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    invoice_number = Column(String(50), unique=True, index=True, nullable=False)
    carrier_id = Column(Integer, ForeignKey("carriers.id"), nullable=False, index=True)
    shipment_id = Column(Integer, ForeignKey("shipments.id"), nullable=True, index=True)
    bol_number_billed = Column(String(50), index=True, nullable=False)
    invoice_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=False)
    currency = Column(String(3), default="USD")
    
    # Financial reconciliation totals
    total_billed_amount = Column(Float, nullable=False, default=0.0)
    calculated_expected_amount = Column(Float, nullable=False, default=0.0)
    total_variance_amount = Column(Float, nullable=False, default=0.0) # billed - expected
    
    # Audit & Lifecycle Status
    status = Column(String(30), default="PENDING_AUDIT", index=True)
    # Statuses: PENDING_AUDIT, VALIDATED_MATCH, EXCEPTION_DISPUTED, EXCEPTION_APPROVED, PAID, REJECTED
    
    validation_status = Column(String(30), default="UNAUDITED") # UNAUDITED, PASSED, FAILED
    is_duplicate = Column(Boolean, default=False)
    duplicate_of_invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=True)
    fingerprint_hash = Column(String(64), index=True, nullable=True) # SHA-256 (carrier_code + bol + total_billed)
    
    reconciliation_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    validated_at = Column(DateTime, nullable=True)

    # Relationships
    carrier = relationship("Carrier", back_populates="invoices")
    shipment = relationship("Shipment", back_populates="invoices")
    lines = relationship("InvoiceLine", back_populates="invoice", cascade="all, delete-orphan")
    exceptions = relationship("InvoiceException", back_populates="invoice", cascade="all, delete-orphan")
    credit_notes = relationship("CreditNote", back_populates="original_invoice")


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True)
    line_number = Column(Integer, nullable=False)
    charge_type = Column(String(30), nullable=False, index=True) # LINEHAUL, FUEL_SURCHARGE, ACCESSORIAL, MISC
    charge_code = Column(String(30), nullable=True) # E.g. LH, FSC, LIFTGATE, DETENTION
    description = Column(String(200), nullable=False)
    
    # Billed Values
    billed_units = Column(Float, default=1.0) # e.g. CWT, miles, hours
    billed_rate = Column(Float, default=0.0)
    billed_amount = Column(Float, nullable=False, default=0.0)
    
    # Contractually Expected Values
    expected_units = Column(Float, default=1.0)
    expected_rate = Column(Float, default=0.0)
    expected_amount = Column(Float, nullable=False, default=0.0)
    
    # Line Variance
    variance_amount = Column(Float, nullable=False, default=0.0) # billed - expected
    status = Column(String(30), default="PENDING") # PENDING, MATCH, VARIANCE_DISCREPANCY, UNAUTHORIZED
    discrepancy_reason = Column(String(255), nullable=True)

    invoice = relationship("InvoiceHeader", back_populates="lines")
    exceptions = relationship("InvoiceException", back_populates="invoice_line")
