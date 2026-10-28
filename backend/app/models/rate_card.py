from datetime import datetime, date
from sqlalchemy import Column, Integer, String, Float, Boolean, Date, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from backend.app.core.database import Base

class RateCard(Base):
    __tablename__ = "rate_cards"

    id = Column(Integer, primary_key=True, index=True)
    rate_card_code = Column(String(50), unique=True, index=True, nullable=False)
    carrier_id = Column(Integer, ForeignKey("carriers.id", ondelete="CASCADE"), nullable=False, index=True)
    effective_date = Column(Date, nullable=False)
    expiration_date = Column(Date, nullable=False)
    currency = Column(String(3), default="USD")
    base_rate_model = Column(String(20), default="PER_CWT") # PER_CWT, PER_MILE, FLAT
    minimum_charge_floor = Column(Float, default=75.0)
    fuel_base_price = Column(Float, default=3.00) # Baseline diesel peg ($/gal)
    fuel_surcharge_pct_per_interval = Column(Float, default=0.005) # 0.5% per $0.05 index move
    status = Column(String(20), default="ACTIVE") # ACTIVE, EXPIRED, SUPERSEDED
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    carrier = relationship("Carrier", back_populates="rate_cards")
    lanes = relationship("RateLane", back_populates="rate_card", cascade="all, delete-orphan")


class RateLane(Base):
    __tablename__ = "rate_lanes"

    id = Column(Integer, primary_key=True, index=True)
    rate_card_id = Column(Integer, ForeignKey("rate_cards.id", ondelete="CASCADE"), nullable=False, index=True)
    origin_zip_prefix = Column(String(5), index=True, default="ALL") # 3-digit zip or "ALL"
    dest_zip_prefix = Column(String(5), index=True, default="ALL")
    origin_region = Column(String(50), nullable=True)
    dest_region = Column(String(50), nullable=True)
    base_rate_cwt = Column(Float, default=12.50) # Rate per 100 lbs
    base_rate_per_mile = Column(Float, default=2.25)
    flat_rate = Column(Float, default=0.0)
    minimum_charge = Column(Float, default=85.0)
    transit_days = Column(Integer, default=2)

    # Relationships
    rate_card = relationship("RateCard", back_populates="lanes")


class AccessorialRule(Base):
    __tablename__ = "accessorial_rules"

    id = Column(Integer, primary_key=True, index=True)
    carrier_id = Column(Integer, ForeignKey("carriers.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(30), nullable=False, index=True) # LIFTGATE, DETENTION, RESIDENTIAL, INSIDE_DELIVERY, RECONSIGNMENT, HAZMAT, APPOINTMENT
    name = Column(String(100), nullable=False)
    rate_type = Column(String(20), default="FLAT") # FLAT, PER_HOUR, PER_CWT, PERCENTAGE
    unit_rate = Column(Float, default=50.0)
    free_time_minutes = Column(Integer, default=0) # E.g. 120 for detention
    min_charge = Column(Float, default=0.0)
    max_charge = Column(Float, nullable=True)
    proof_required = Column(Boolean, default=True) # Must match POD/GPS log
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    carrier = relationship("Carrier", back_populates="accessorial_rules")
