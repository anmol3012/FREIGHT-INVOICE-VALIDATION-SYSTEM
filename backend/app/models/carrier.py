from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import relationship
from backend.app.core.database import Base

class Carrier(Base):
    __tablename__ = "carriers"

    id = Column(Integer, primary_key=True, index=True)
    carrier_code = Column(String(10), unique=True, index=True, nullable=False) # e.g. SCAC
    name = Column(String(100), nullable=False)
    tax_id = Column(String(30), nullable=False)
    payment_terms_days = Column(Integer, default=30)
    status = Column(String(20), default="ACTIVE") # ACTIVE, SUSPENDED
    contact_email = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    rate_cards = relationship("RateCard", back_populates="carrier", cascade="all, delete-orphan")
    accessorial_rules = relationship("AccessorialRule", back_populates="carrier", cascade="all, delete-orphan")
    shipments = relationship("Shipment", back_populates="carrier")
    invoices = relationship("InvoiceHeader", back_populates="carrier")
    credit_notes = relationship("CreditNote", back_populates="carrier")
