from datetime import datetime
from sqlalchemy import Column, String, DateTime, Enum as SAEnum
from sqlalchemy.orm import relationship
from backend.app.core.database import Base
from backend.app.models.enums import CarrierStatus

class Carrier(Base):
    """
    Carrier entity representing transportation service providers.
    PK format: CAR-000001
    """
    __tablename__ = "carriers"

    carrier_id = Column(String(30), primary_key=True, index=True)
    carrier_name = Column(String(100), nullable=False)
    carrier_code = Column(String(10), unique=True, index=True, nullable=False) # e.g. SCAC
    status = Column(SAEnum(CarrierStatus), nullable=False, default=CarrierStatus.ACTIVE)
    country_code = Column(String(3), nullable=False, default="USA")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    rate_cards = relationship("RateCard", back_populates="carrier", cascade="all, delete-orphan")
    shipments = relationship("Shipment", back_populates="carrier")
    invoices = relationship("FreightInvoice", back_populates="carrier")
    credit_notes = relationship("CreditNote", back_populates="carrier")
    duplicate_groups = relationship("DuplicateInvoiceGroup", back_populates="carrier")
