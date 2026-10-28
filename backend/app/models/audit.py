from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text
from backend.app.core.database import Base

class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(Integer, primary_key=True, index=True)
    entity_type = Column(String(50), nullable=False, index=True) # INVOICE, EXCEPTION, CREDIT_NOTE, RATE_CARD, SHIPMENT
    entity_id = Column(String(50), nullable=False, index=True)
    event_type = Column(String(50), nullable=False, index=True) # CREATED, VALIDATED, EXCEPTION_RAISED, DISPUTED, RESOLVED, CREDIT_APPLIED
    actor = Column(String(50), default="SYSTEM_AUDITOR") # SYSTEM_AUDITOR, OPERATOR, DATA_GENERATOR
    payload_json = Column(Text, nullable=True) # Snapshot / diff
    notes = Column(String(255), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
