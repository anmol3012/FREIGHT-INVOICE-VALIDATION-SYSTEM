from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text
from backend.app.core.database import Base

class AuditEvent(Base):
    """
    Immutable, append-only operational audit event log.
    PK format: AUD-2026-000001
    """
    __tablename__ = "audit_events"

    event_id = Column(String(40), primary_key=True, index=True)
    entity_type = Column(String(50), nullable=False, index=True) # FREIGHT_INVOICE, AUDIT_EXCEPTION, CREDIT_NOTE, CARRIER, SHIPMENT
    entity_id = Column(String(50), nullable=False, index=True)
    event_type = Column(String(50), nullable=False, index=True) # CREATED, VALIDATION_RUN, STATUS_CHANGED, DISPUTE_RAISED, CREDIT_APPLIED
    actor = Column(String(50), nullable=False, default="SYSTEM_AUDITOR")
    payload_json = Column(Text, nullable=True) # Full structured snapshot / diff
    notes = Column(String(255), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class EntityStatusHistory(Base):
    """
    Explicit lifecycle transition log preserving every status change across entities.
    PK format: HIST-2026-000001
    """
    __tablename__ = "entity_status_history"

    history_id = Column(String(40), primary_key=True, index=True)
    entity_name = Column(String(50), nullable=False, index=True) # Shipment, FreightInvoice, AuditException, CreditNote
    entity_id = Column(String(50), nullable=False, index=True)
    from_status = Column(String(50), nullable=False)
    to_status = Column(String(50), nullable=False)
    transition_reason = Column(String(255), nullable=True)
    changed_by = Column(String(50), nullable=False, default="SYSTEM_AUDITOR")
    changed_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
