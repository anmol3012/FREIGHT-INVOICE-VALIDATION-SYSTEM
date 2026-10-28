from datetime import datetime, date
from sqlalchemy import Column, String, Float, Boolean, Date, DateTime, ForeignKey, CheckConstraint, Integer, UniqueConstraint, Text, Enum as SAEnum
from sqlalchemy.orm import relationship
from backend.app.core.database import Base
from backend.app.models.enums import (
    InvoiceStatus, ValidationStatus, InvoiceLineType
)

class DuplicateInvoiceGroup(Base):
    """
    Tracks duplicate billing clusters and canonical invoices.
    PK format: DUP-000001
    """
    __tablename__ = "duplicate_invoice_groups"

    group_id = Column(String(30), primary_key=True, index=True)
    carrier_id = Column(String(30), ForeignKey("carriers.carrier_id"), nullable=False, index=True)
    fingerprint_hash = Column(String(64), unique=True, index=True, nullable=False)
    canonical_invoice_id = Column(String(40), nullable=True) # First seen legitimate invoice ID
    invoice_count = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    carrier = relationship("Carrier", back_populates="duplicate_groups")
    invoices = relationship("FreightInvoice", back_populates="duplicate_group")


class FreightInvoice(Base):
    """
    Normalized Freight Invoice header submitted by carrier.
    PK format: FINV-2026-000001
    """
    __tablename__ = "freight_invoices"

    invoice_id = Column(String(40), primary_key=True, index=True)
    carrier_id = Column(String(30), ForeignKey("carriers.carrier_id"), nullable=False, index=True)
    
    # Shipment reference handling:
    # Staging/import untrusted reference persisted in raw_shipment_reference.
    # Persist normalized FK only if valid; if deliberately invalid/unmatched, shipment_id is NULL.
    shipment_id = Column(String(30), ForeignKey("shipments.shipment_id"), nullable=True, index=True)
    raw_shipment_reference = Column(String(50), nullable=False, index=True) # e.g. "SHP-2026-000001" or invalid "SHP-FAKE-999"
    reference_rejection_reason = Column(String(255), nullable=True) # e.g. "External shipment ID does not exist in master records"

    invoice_number = Column(String(50), nullable=False, index=True)
    invoice_date = Column(Date, nullable=False, index=True)
    service_period_start = Column(Date, nullable=False)
    service_period_end = Column(Date, nullable=False)
    due_date = Column(Date, nullable=False)
    currency = Column(String(3), nullable=False, default="USD")

    # Financial Reconciliation Totals
    billed_total = Column(Float, nullable=False, default=0.0)
    expected_total = Column(Float, nullable=False, default=0.0)
    variance_amount = Column(Float, nullable=False, default=0.0) # billed - expected

    invoice_status = Column(SAEnum(InvoiceStatus), nullable=False, default=InvoiceStatus.SUBMITTED, index=True)
    validation_status = Column(SAEnum(ValidationStatus), nullable=False, default=ValidationStatus.UNAUDITED, index=True)
    
    duplicate_group_id = Column(String(30), ForeignKey("duplicate_invoice_groups.group_id"), nullable=True, index=True)
    fingerprint_hash = Column(String(64), index=True, nullable=True) # SHA-256 (carrier_id + raw_shipment_ref + billed_total)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("carrier_id", "invoice_number", name="uq_carrier_invoice_number"),
        CheckConstraint("service_period_start <= service_period_end", name="chk_inv_valid_service_period"),
        CheckConstraint("billed_total >= 0", name="chk_inv_nonnegative_billed_total"),
        CheckConstraint("expected_total >= 0", name="chk_inv_nonnegative_expected_total"),
    )

    # Relationships
    carrier = relationship("Carrier", back_populates="invoices")
    shipment = relationship("Shipment", back_populates="invoices")
    duplicate_group = relationship("DuplicateInvoiceGroup", back_populates="invoices")
    invoice_lines = relationship("InvoiceLine", back_populates="invoice", cascade="all, delete-orphan", order_by="InvoiceLine.line_number")
    audit_exceptions = relationship("AuditException", back_populates="invoice", cascade="all, delete-orphan")
    credit_notes = relationship("CreditNote", back_populates="invoice")
    validation_runs = relationship("InvoiceValidationRun", back_populates="invoice", cascade="all, delete-orphan")


class InvoiceLine(Base):
    """
    Itemized charges on a FreightInvoice.
    PK format: FLINE-FINV-2026-000001-01
    """
    __tablename__ = "invoice_lines"

    invoice_line_id = Column(String(50), primary_key=True, index=True)
    invoice_id = Column(String(40), ForeignKey("freight_invoices.invoice_id", ondelete="CASCADE"), nullable=False, index=True)
    line_number = Column(Integer, nullable=False)
    line_type = Column(SAEnum(InvoiceLineType), nullable=False, default=InvoiceLineType.BASE_LINEHAUL)
    accessorial_id = Column(String(30), ForeignKey("accessorials.accessorial_id"), nullable=True, index=True)
    description = Column(String(200), nullable=False)
    
    quantity = Column(Float, nullable=False, default=1.0)
    unit_of_measure = Column(String(20), nullable=False, default="KG") # KG, KM, HOUR, FLAT
    unit_rate = Column(Float, nullable=False, default=0.0)
    billed_amount = Column(Float, nullable=False, default=0.0)
    expected_amount = Column(Float, nullable=False, default=0.0)
    variance_amount = Column(Float, nullable=False, default=0.0) # billed - expected

    evidence_reference = Column(String(100), nullable=True) # e.g. "POD-SIGNED-DOCK-DOC"
    source_reference = Column(String(100), nullable=True) # e.g. "RATE-CAR-000001-2026-01"
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("invoice_id", "line_number", name="uq_invoice_line_number"),
        CheckConstraint("line_number >= 1", name="chk_line_number_positive"),
        CheckConstraint("billed_amount >= 0", name="chk_line_nonnegative_billed"),
        CheckConstraint("expected_amount >= 0", name="chk_line_nonnegative_expected"),
    )

    # Relationships
    invoice = relationship("FreightInvoice", back_populates="invoice_lines")
    accessorial = relationship("Accessorial", back_populates="invoice_lines")
    audit_exceptions = relationship("AuditException", back_populates="invoice_line")


class InvoiceValidationRun(Base):
    """
    Records an execution of the validation engine on an invoice.
    PK format: VRUN-2026-000001
    """
    __tablename__ = "invoice_validation_runs"

    validation_run_id = Column(String(40), primary_key=True, index=True)
    invoice_id = Column(String(40), ForeignKey("freight_invoices.invoice_id", ondelete="CASCADE"), nullable=False, index=True)
    run_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    actor = Column(String(50), nullable=False, default="SYSTEM_AUDITOR")
    rules_applied_count = Column(Integer, nullable=False, default=0)
    exceptions_detected_count = Column(Integer, nullable=False, default=0)
    summary_verdict = Column(String(30), nullable=False) # PASSED, FAILED
    details_json = Column(Text, nullable=True)

    invoice = relationship("FreightInvoice", back_populates="validation_runs")
