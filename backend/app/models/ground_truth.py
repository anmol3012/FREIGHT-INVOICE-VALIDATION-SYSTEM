from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Boolean
from backend.app.core.database import Base

class GroundTruthLabel(Base):
    """
    Independently stored ground-truth labels.
    Never consumed by operational calculation or validation routines.
    Only queried by the evaluation module to measure audit precision, recall, and detection accuracy.
    """
    __tablename__ = "ground_truth_labels"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, index=True, nullable=True)
    invoice_number = Column(String(50), index=True, nullable=False)
    bol_number = Column(String(50), index=True, nullable=False)
    carrier_code = Column(String(10), index=True, nullable=False)
    
    # Negative scenario category or NORMAL:
    # 1. BASE_RATE_MISMATCH
    # 2. WEIGHT_DISCREPANCY
    # 3. UNAUTHORIZED_ACCESSORIAL
    # 4. DUPLICATE_BILLING
    # 5. INVALID_CREDIT_NOTE
    # or NORMAL
    scenario_type = Column(String(50), nullable=False, index=True)
    is_anomaly = Column(Boolean, nullable=False, default=False)
    expected_verdict = Column(String(20), nullable=False) # PASS, FAIL
    
    ground_truth_billed = Column(Float, nullable=False)
    ground_truth_expected = Column(Float, nullable=False)
    injected_variance = Column(Float, nullable=False, default=0.0)
    
    anomaly_details_json = Column(Text, nullable=True) # Full metadata of what was manipulated
    created_at = Column(DateTime, default=datetime.utcnow)
