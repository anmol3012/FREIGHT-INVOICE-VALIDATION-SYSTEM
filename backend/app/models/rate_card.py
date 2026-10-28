from datetime import datetime, date
from sqlalchemy import Column, String, Float, Date, DateTime, ForeignKey, CheckConstraint, Integer, UniqueConstraint, Enum as SAEnum
from sqlalchemy.orm import relationship
from backend.app.core.database import Base
from backend.app.models.enums import RateCardStatus, ServiceLevel

class RateCard(Base):
    """
    Contracted freight tariff schedule for a carrier on a specific lane & service level.
    PK format: RATE-CAR-000001-2026-01
    """
    __tablename__ = "rate_cards"

    rate_card_id = Column(String(50), primary_key=True, index=True)
    carrier_id = Column(String(30), ForeignKey("carriers.carrier_id", ondelete="CASCADE"), nullable=False, index=True)
    lane_id = Column(String(30), ForeignKey("lanes.lane_id", ondelete="CASCADE"), nullable=False, index=True)
    service_level = Column(SAEnum(ServiceLevel), nullable=False, default=ServiceLevel.STANDARD, index=True)
    currency = Column(String(3), nullable=False, default="USD")
    effective_from = Column(Date, nullable=False, index=True)
    effective_to = Column(Date, nullable=True, index=True) # Nullable = open-ended. Inclusive if specified.
    base_rate = Column(Float, nullable=False)
    minimum_charge = Column(Float, nullable=False)
    dimensional_weight_divisor = Column(Float, nullable=False, default=5000.0) # standard metric divisor 5000 cm3/kg
    status = Column(SAEnum(RateCardStatus), nullable=False, default=RateCardStatus.ACTIVE)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("base_rate >= 0", name="chk_rate_card_nonnegative_base_rate"),
        CheckConstraint("minimum_charge >= 0", name="chk_rate_card_nonnegative_min_charge"),
        CheckConstraint("dimensional_weight_divisor > 0", name="chk_rate_card_positive_dim_divisor"),
        CheckConstraint("(effective_to IS NULL) OR (effective_from <= effective_to)", name="chk_rate_card_valid_dates"),
    )

    # Relationships
    carrier = relationship("Carrier", back_populates="rate_cards")
    lane = relationship("Lane", back_populates="rate_cards")
    rate_tiers = relationship("RateTier", back_populates="rate_card", cascade="all, delete-orphan", order_by="RateTier.tier_sequence")


class RateTier(Base):
    """
    Weight-break tiers and tier-specific rates for a RateCard.
    PK format: TIER-RATE-CAR-000001-2026-01-01
    """
    __tablename__ = "rate_tiers"

    rate_tier_id = Column(String(60), primary_key=True, index=True)
    rate_card_id = Column(String(50), ForeignKey("rate_cards.rate_card_id", ondelete="CASCADE"), nullable=False, index=True)
    tier_sequence = Column(Integer, nullable=False)
    min_weight_kg = Column(Float, nullable=False)
    max_weight_kg = Column(Float, nullable=True) # None = open-ended upper bracket
    rate_per_kg = Column(Float, nullable=False)
    flat_surcharge = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("rate_card_id", "tier_sequence", name="uq_rate_tier_sequence"),
        CheckConstraint("min_weight_kg >= 0", name="chk_tier_nonnegative_min_weight"),
        CheckConstraint("(max_weight_kg IS NULL) OR (min_weight_kg < max_weight_kg)", name="chk_tier_valid_weight_range"),
        CheckConstraint("rate_per_kg >= 0", name="chk_tier_nonnegative_rate"),
        CheckConstraint("flat_surcharge >= 0", name="chk_tier_nonnegative_surcharge"),
    )

    rate_card = relationship("RateCard", back_populates="rate_tiers")
