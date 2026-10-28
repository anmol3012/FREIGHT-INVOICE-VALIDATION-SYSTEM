from datetime import datetime, date
from sqlalchemy import Column, String, Float, Boolean, Date, DateTime, ForeignKey, CheckConstraint, Integer, UniqueConstraint, Enum as SAEnum
from sqlalchemy.orm import relationship
from backend.app.core.database import Base
from backend.app.models.enums import (
    ShipmentStatus, ShipmentLegStatus, ServiceLevel, MeasurementType, MeasurementSource
)

class Shipment(Base):
    """
    Physical shipment transportation event.
    PK format: SHP-2026-000001
    """
    __tablename__ = "shipments"

    shipment_id = Column(String(30), primary_key=True, index=True)
    carrier_id = Column(String(30), ForeignKey("carriers.carrier_id"), nullable=False, index=True)
    lane_id = Column(String(30), ForeignKey("lanes.lane_id"), nullable=False, index=True)
    service_level = Column(SAEnum(ServiceLevel), nullable=False, default=ServiceLevel.STANDARD, index=True)
    ship_date = Column(Date, nullable=False, index=True)
    delivery_due_date = Column(Date, nullable=False)
    delivered_at = Column(DateTime, nullable=True)
    
    # Dimensions and Weights (Metric)
    actual_length_cm = Column(Float, nullable=False)
    actual_width_cm = Column(Float, nullable=False)
    actual_height_cm = Column(Float, nullable=False)
    actual_weight_kg = Column(Float, nullable=False)
    declared_weight_kg = Column(Float, nullable=False)
    chargeable_weight_kg = Column(Float, nullable=False)
    
    currency = Column(String(3), nullable=False, default="USD")
    shipment_status = Column(SAEnum(ShipmentStatus), nullable=False, default=ShipmentStatus.BOOKED, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("actual_length_cm > 0", name="chk_shipment_positive_length"),
        CheckConstraint("actual_width_cm > 0", name="chk_shipment_positive_width"),
        CheckConstraint("actual_height_cm > 0", name="chk_shipment_positive_height"),
        CheckConstraint("actual_weight_kg > 0", name="chk_shipment_positive_act_weight"),
        CheckConstraint("declared_weight_kg > 0", name="chk_shipment_positive_dec_weight"),
        CheckConstraint("chargeable_weight_kg > 0", name="chk_shipment_positive_chg_weight"),
        CheckConstraint("ship_date <= delivery_due_date", name="chk_shipment_valid_dates"),
    )

    # Relationships
    carrier = relationship("Carrier", back_populates="shipments")
    lane = relationship("Lane", back_populates="shipments")
    shipment_legs = relationship("ShipmentLeg", back_populates="shipment", cascade="all, delete-orphan", order_by="ShipmentLeg.leg_sequence")
    weight_measurements = relationship("WeightMeasurement", back_populates="shipment", cascade="all, delete-orphan")
    shipment_accessorials = relationship("ShipmentAccessorial", back_populates="shipment", cascade="all, delete-orphan")
    delivery_evidence = relationship("DeliveryEvidence", back_populates="shipment", uselist=False, cascade="all, delete-orphan")
    invoices = relationship("FreightInvoice", back_populates="shipment")
    audit_exceptions = relationship("AuditException", back_populates="shipment")


class ShipmentLeg(Base):
    """
    Sub-movement segments of a shipment.
    PK format: LEG-SHP-2026-000001-01
    """
    __tablename__ = "shipment_legs"

    shipment_leg_id = Column(String(40), primary_key=True, index=True)
    shipment_id = Column(String(30), ForeignKey("shipments.shipment_id", ondelete="CASCADE"), nullable=False, index=True)
    leg_sequence = Column(Integer, nullable=False)
    origin_location_code = Column(String(20), nullable=False)
    destination_location_code = Column(String(20), nullable=False)
    departure_at = Column(DateTime, nullable=True)
    arrival_at = Column(DateTime, nullable=True)
    leg_status = Column(SAEnum(ShipmentLegStatus), nullable=False, default=ShipmentLegStatus.PENDING)

    __table_args__ = (
        UniqueConstraint("shipment_id", "leg_sequence", name="uq_shipment_leg_sequence"),
        CheckConstraint("leg_sequence >= 1", name="chk_leg_sequence_positive"),
        CheckConstraint("(departure_at IS NULL OR arrival_at IS NULL) OR (departure_at <= arrival_at)", name="chk_leg_valid_timestamps"),
    )

    shipment = relationship("Shipment", back_populates="shipment_legs")


class WeightMeasurement(Base):
    """
    Weight measurement certificates and scale readings.
    PK format: WM-SHP-2026-000001-01
    """
    __tablename__ = "weight_measurements"

    weight_measurement_id = Column(String(40), primary_key=True, index=True)
    shipment_id = Column(String(30), ForeignKey("shipments.shipment_id", ondelete="CASCADE"), nullable=False, index=True)
    measurement_type = Column(SAEnum(MeasurementType), nullable=False, default=MeasurementType.ORIGIN_SCALE)
    length_cm = Column(Float, nullable=True)
    width_cm = Column(Float, nullable=True)
    height_cm = Column(Float, nullable=True)
    weight_kg = Column(Float, nullable=False)
    measured_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    source = Column(SAEnum(MeasurementSource), nullable=False, default=MeasurementSource.CARRIER)
    is_accepted = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        CheckConstraint("weight_kg > 0", name="chk_wm_positive_weight"),
        CheckConstraint("(length_cm IS NULL) OR (length_cm > 0)", name="chk_wm_positive_length"),
        CheckConstraint("(width_cm IS NULL) OR (width_cm > 0)", name="chk_wm_positive_width"),
        CheckConstraint("(height_cm IS NULL) OR (height_cm > 0)", name="chk_wm_positive_height"),
    )

    shipment = relationship("Shipment", back_populates="weight_measurements")


class DeliveryEvidence(Base):
    """
    Destination Delivery Proof (POD) and physical facility evidence.
    PK format: DEV-SHP-2026-000001
    """
    __tablename__ = "delivery_evidence"

    delivery_evidence_id = Column(String(40), primary_key=True, index=True)
    shipment_id = Column(String(30), ForeignKey("shipments.shipment_id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    delivered_at = Column(DateTime, nullable=False)
    recipient_name = Column(String(100), nullable=False)
    signed_pod_ref = Column(String(100), nullable=True)
    facility_dock_type = Column(String(50), nullable=False, default="STANDARD_DOCK") # STANDARD_DOCK, GROUND_LEVEL, RESIDENTIAL
    liftgate_actually_used = Column(Boolean, nullable=False, default=False)
    detention_minutes_recorded = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("detention_minutes_recorded >= 0", name="chk_dev_nonnegative_detention"),
    )

    shipment = relationship("Shipment", back_populates="delivery_evidence")
