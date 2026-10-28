from datetime import datetime
from sqlalchemy import Column, String, Float, DateTime, Text, Boolean
from backend.app.core.database import Base

class GroundTruthLabel(Base):
    """
    Independently stored ground-truth labels for audit accuracy benchmarking.
    Never consumed by operational calculation or validation routines.
    PK format: GTL-2026-000001
    """
    __tablename__ = "ground_truth_labels"

    label_id = Column(String(40), primary_key=True, index=True)
    anomaly_id = Column(String(40), index=True, nullable=True) # e.g. ANOM-2026-000001 or None for NORMAL
    invoice_id = Column(String(40), index=True, nullable=False)
    invoice_number = Column(String(50), index=True, nullable=False)
    raw_shipment_reference = Column(String(50), index=True, nullable=False)
    carrier_id = Column(String(30), index=True, nullable=False)
    carrier_code = Column(String(10), index=True, nullable=False)

    issue_type = Column(String(50), nullable=False, index=True)
    is_anomaly = Column(Boolean, nullable=False, default=False)
    expected_decision = Column(String(20), nullable=False) # PASS, FAIL

    affected_entity_ids_json = Column(Text, nullable=True)
    injection_method = Column(Text, nullable=True)

    ground_truth_billed = Column(Float, nullable=False)
    ground_truth_expected = Column(Float, nullable=False)
    injected_variance = Column(Float, nullable=False, default=0.0)

    details_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
