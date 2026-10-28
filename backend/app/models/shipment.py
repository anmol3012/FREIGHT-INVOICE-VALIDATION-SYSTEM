from datetime import datetime, date
from sqlalchemy import Column, Integer, String, Float, Boolean, Date, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from backend.app.core.database import Base

class Shipment(Base):
    __tablename__ = "shipments"

    id = Column(Integer, primary_key=True, index=True)
    bol_number = Column(String(50), unique=True, index=True, nullable=False) # Bill of Lading
    carrier_id = Column(Integer, ForeignKey("carriers.id"), nullable=False, index=True)
    origin_zip = Column(String(10), nullable=False)
    origin_city = Column(String(50), nullable=False)
    origin_state = Column(String(10), nullable=False)
    destination_zip = Column(String(10), nullable=False)
    destination_city = Column(String(50), nullable=False)
    destination_state = Column(String(10), nullable=False)
    pickup_date = Column(Date, nullable=False)
    delivery_date = Column(Date, nullable=False)
    distance_miles = Column(Float, default=250.0)
    current_fuel_index = Column(Float, default=3.85) # Diesel price at shipment time
    service_level = Column(String(20), default="STANDARD") # STANDARD, EXPEDITED
    dock_type = Column(String(30), default="STANDARD_DOCK") # STANDARD_DOCK, RESIDENTIAL, GROUND_LEVEL
    status = Column(String(20), default="DELIVERED") # BOOKED, IN_TRANSIT, DELIVERED, CANCELLED
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    carrier = relationship("Carrier", back_populates="shipments")
    weight_measurements = relationship("WeightMeasurement", back_populates="shipment", cascade="all, delete-orphan")
    accessorial_events = relationship("AccessorialEvent", back_populates="shipment", cascade="all, delete-orphan")
    delivery_record = relationship("DeliveryRecord", back_populates="shipment", uselist=False, cascade="all, delete-orphan")
    invoices = relationship("InvoiceHeader", back_populates="shipment")


class WeightMeasurement(Base):
    __tablename__ = "weight_measurements"

    id = Column(Integer, primary_key=True, index=True)
    shipment_id = Column(Integer, ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False, index=True)
    measurement_type = Column(String(30), default="ORIGIN_SCALE") # ORIGIN_SCALE, CARRIER_REWEIGH, DIMENSIONAL
    gross_weight_lbs = Column(Float, nullable=False)
    length_in = Column(Float, default=48.0)
    width_in = Column(Float, default=40.0)
    height_in = Column(Float, default=48.0)
    dim_factor = Column(Float, default=139.0) # standard freight dim factor cu in / lb
    billable_weight_lbs = Column(Float, nullable=False)
    certified = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    shipment = relationship("Shipment", back_populates="weight_measurements")


class AccessorialEvent(Base):
    __tablename__ = "accessorial_events"

    id = Column(Integer, primary_key=True, index=True)
    shipment_id = Column(Integer, ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(30), nullable=False) # LIFTGATE, DETENTION, RESIDENTIAL, etc.
    quantity_or_duration = Column(Float, default=1.0) # E.g. hours or units
    proof_document_ref = Column(String(100), nullable=True) # e.g. BOL-POD-SIGNED, GPS-IN-GATE
    authorized = Column(Boolean, default=True)
    notes = Column(String(200), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    shipment = relationship("Shipment", back_populates="accessorial_events")


class DeliveryRecord(Base):
    __tablename__ = "delivery_records"

    id = Column(Integer, primary_key=True, index=True)
    shipment_id = Column(Integer, ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False, index=True)
    delivered_at = Column(DateTime, nullable=False)
    recipient_name = Column(String(100), nullable=False)
    signed_pod_ref = Column(String(100), nullable=True)
    facility_dock_type = Column(String(50), default="STANDARD_DOCK") # STANDARD_DOCK, GROUND_LEVEL, RESIDENTIAL
    liftgate_actually_used = Column(Boolean, default=False)
    detention_minutes_recorded = Column(Integer, default=0) # ELD/GPS dwell time
    created_at = Column(DateTime, default=datetime.utcnow)

    shipment = relationship("Shipment", back_populates="delivery_record")
