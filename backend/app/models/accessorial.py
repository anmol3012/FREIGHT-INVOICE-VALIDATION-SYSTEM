from datetime import datetime, date
from sqlalchemy import Column, String, Float, Boolean, Date, DateTime, ForeignKey, CheckConstraint, Enum as SAEnum
from sqlalchemy.orm import relationship
from backend.app.core.database import Base
from backend.app.models.enums import AccessorialStatus, ChargeMethod

class Accessorial(Base):
    """
    Contractual definition of accessorial services and secondary fees.
    PK format: ACC-000001
    """
    __tablename__ = "accessorials"

    accessorial_id = Column(String(30), primary_key=True, index=True)
    accessorial_code = Column(String(30), unique=True, index=True, nullable=False) # e.g. LIFTGATE, DETENTION, RESIDENTIAL
    description = Column(String(200), nullable=False)
    charge_method = Column(SAEnum(ChargeMethod), nullable=False, default=ChargeMethod.FLAT)
    rate_amount = Column(Float, nullable=False)
    currency = Column(String(3), nullable=False, default="USD")
    taxable = Column(Boolean, nullable=False, default=False)
    requires_evidence = Column(Boolean, nullable=False, default=True) # Must match delivery record / ELD GPS log
    status = Column(SAEnum(AccessorialStatus), nullable=False, default=AccessorialStatus.ACTIVE)
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date, nullable=True) # Nullable = open-ended

    __table_args__ = (
        CheckConstraint("rate_amount >= 0", name="chk_accessorial_nonnegative_rate"),
        CheckConstraint("(effective_to IS NULL) OR (effective_from <= effective_to)", name="chk_accessorial_valid_dates"),
    )

    # Relationships
    shipment_accessorials = relationship("ShipmentAccessorial", back_populates="accessorial")
    invoice_lines = relationship("InvoiceLine", back_populates="accessorial")


class ShipmentAccessorial(Base):
    """
    Bridge table recording N:M accessorial service occurrences on a Shipment.
    PK format: SA-SHP-2026-000001-01
    """
    __tablename__ = "shipment_accessorials"

    shipment_accessorial_id = Column(String(50), primary_key=True, index=True)
    shipment_id = Column(String(30), ForeignKey("shipments.shipment_id", ondelete="CASCADE"), nullable=False, index=True)
    accessorial_id = Column(String(30), ForeignKey("accessorials.accessorial_id", ondelete="CASCADE"), nullable=False, index=True)
    quantity = Column(Float, nullable=False, default=1.0)
    authorized = Column(Boolean, nullable=False, default=True)
    evidence_reference = Column(String(100), nullable=True) # e.g. "POD-SIGNED-DOCK-DOC"
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("quantity > 0", name="chk_shipment_acc_positive_quantity"),
    )

    shipment = relationship("Shipment", back_populates="shipment_accessorials")
    accessorial = relationship("Accessorial", back_populates="shipment_accessorials")
