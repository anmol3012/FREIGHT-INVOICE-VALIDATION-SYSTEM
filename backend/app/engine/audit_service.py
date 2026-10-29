"""
Immutable Audit Trail and Lifecycle State Machine Service.
Ensures transactional, append-only persistence of audit events,
lifecycle state transitions, and operator manual overrides.
"""

import json
from datetime import datetime
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session

from backend.app.models.audit import AuditEvent, EntityStatusHistory
from backend.app.models.invoice import FreightInvoice
from backend.app.models.audit_exception import AuditException
from backend.app.models.credit_note import CreditNote
from backend.app.models.enums import (
    InvoiceStatus, ExceptionStatus, CreditNoteReconciliationStatus,
    CreditNoteApprovalStatus, AuditEventType
)
from backend.app.models.lifecycle import (
    validate_invoice_transition, validate_exception_transition,
    validate_credit_note_transition, validate_shipment_transition,
    InvalidStateTransitionError
)
from backend.app.models.id_generator import (
    generate_audit_event_id, generate_status_history_id
)


def _get_max_counter(db: Session, model_col, prefix: str) -> int:
    """Safely computes the next deterministic sequence number from DB records."""
    rows = db.query(model_col).filter(model_col.like(f"{prefix}%")).all()
    if not rows:
        return 1
    max_val = 0
    for (val,) in rows:
        if val:
            try:
                num = int(val.split("-")[-1])
                if num > max_val:
                    max_val = num
            except (ValueError, IndexError):
                pass
    return max_val + 1


class AuditService:
    """
    Central service for immutable audit logging and state progression.
    """

    @classmethod
    def record_audit_event(
        cls,
        db: Session,
        entity_type: str,
        entity_id: str,
        event_type: Any,
        actor: str = "SYSTEM_AUDITOR",
        payload: Optional[Dict[str, Any]] = None,
        notes: Optional[str] = None,
        timestamp: Optional[datetime] = None
    ) -> AuditEvent:
        """
        Appends an immutable audit event to the append-only log.
        """
        ev_type_str = event_type.value if hasattr(event_type, "value") else str(event_type)
        ts = timestamp or datetime.utcnow()
        cnt = _get_max_counter(db, AuditEvent.event_id, "AUD-2026-")
        ev_id = generate_audit_event_id(cnt)

        ev = AuditEvent(
            event_id=ev_id,
            entity_type=entity_type,
            entity_id=entity_id,
            event_type=ev_type_str,
            actor=actor,
            payload_json=json.dumps(payload or {}, sort_keys=True),
            notes=notes,
            timestamp=ts
        )
        db.add(ev)
        db.flush()
        return ev

    @classmethod
    def transition_invoice(
        cls,
        db: Session,
        invoice: FreightInvoice,
        target_status: InvoiceStatus,
        reason: str,
        actor: str = "SYSTEM_AUDITOR",
        metadata: Optional[Dict[str, Any]] = None
    ) -> FreightInvoice:
        """
        Validates and executes an invoice lifecycle state transition.
        Rejects prohibited transitions via InvalidStateTransitionError without corrupting state.
        """
        old_status = invoice.invoice_status
        if old_status == target_status:
            return invoice
        validate_invoice_transition(old_status, target_status)

        invoice.invoice_status = target_status

        # Record explicit lifecycle transition history
        hist_cnt = _get_max_counter(db, EntityStatusHistory.history_id, "HIST-2026-")
        sh = EntityStatusHistory(
            history_id=generate_status_history_id(hist_cnt),
            entity_name="FreightInvoice",
            entity_id=invoice.invoice_id,
            from_status=old_status.value if hasattr(old_status, "value") else str(old_status),
            to_status=target_status.value if hasattr(target_status, "value") else str(target_status),
            transition_reason=reason,
            changed_by=actor,
            changed_at=datetime.utcnow()
        )
        db.add(sh)

        # Record corresponding audit event
        payload = metadata or {}
        payload.update({
            "from_status": old_status.value if hasattr(old_status, "value") else str(old_status),
            "to_status": target_status.value if hasattr(target_status, "value") else str(target_status),
            "reason": reason
        })
        cls.record_audit_event(
            db=db,
            entity_type="FreightInvoice",
            entity_id=invoice.invoice_id,
            event_type=AuditEventType.INVOICE_STATUS_CHANGED,
            actor=actor,
            payload=payload,
            notes=f"Invoice status transitioned from {old_status.value} to {target_status.value}."
        )

        db.flush()
        return invoice

    @classmethod
    def transition_exception(
        cls,
        db: Session,
        exception: AuditException,
        target_status: ExceptionStatus,
        reason: str,
        actor: str = "DISPUTE_MANAGER",
        metadata: Optional[Dict[str, Any]] = None
    ) -> AuditException:
        """
        Validates and executes an audit exception lifecycle transition.
        """
        old_status = exception.exception_status
        if old_status == target_status:
            return exception
        validate_exception_transition(old_status, target_status)

        exception.exception_status = target_status
        if target_status in [ExceptionStatus.AUTO_RESOLVED, ExceptionStatus.APPROVED_OVERRIDE, ExceptionStatus.REJECTED]:
            exception.resolved_at = datetime.utcnow()

        # Record explicit lifecycle history
        hist_cnt = _get_max_counter(db, EntityStatusHistory.history_id, "HIST-2026-")
        sh = EntityStatusHistory(
            history_id=generate_status_history_id(hist_cnt),
            entity_name="AuditException",
            entity_id=exception.exception_id,
            from_status=old_status.value if hasattr(old_status, "value") else str(old_status),
            to_status=target_status.value if hasattr(target_status, "value") else str(target_status),
            transition_reason=reason,
            changed_by=actor,
            changed_at=datetime.utcnow()
        )
        db.add(sh)

        # Map to specific audit event
        if target_status == ExceptionStatus.APPROVED_OVERRIDE:
            ev_type = AuditEventType.EXCEPTION_APPROVED
        elif target_status == ExceptionStatus.REJECTED:
            ev_type = AuditEventType.EXCEPTION_REJECTED
        elif target_status == ExceptionStatus.AUTO_RESOLVED:
            ev_type = AuditEventType.EXCEPTION_RESOLVED
        else:
            ev_type = AuditEventType.EXCEPTION_ASSIGNED

        payload = metadata or {}
        payload.update({
            "from_status": old_status.value if hasattr(old_status, "value") else str(old_status),
            "to_status": target_status.value if hasattr(target_status, "value") else str(target_status),
            "reason": reason,
            "disputed_amount": exception.disputed_amount
        })
        cls.record_audit_event(
            db=db,
            entity_type="AuditException",
            entity_id=exception.exception_id,
            event_type=ev_type,
            actor=actor,
            payload=payload,
            notes=f"Exception {exception.exception_id} transitioned to {target_status.value}: {reason}"
        )

        db.flush()
        return exception

    @classmethod
    def transition_credit_note(
        cls,
        db: Session,
        credit_note: CreditNote,
        target_reconciliation_status: CreditNoteReconciliationStatus,
        reason: str,
        actor: str = "CREDIT_AUDITOR",
        metadata: Optional[Dict[str, Any]] = None
    ) -> CreditNote:
        """
        Validates and executes a credit note reconciliation state progression.
        """
        old_status = credit_note.reconciliation_status
        if old_status == target_reconciliation_status:
            return credit_note
        validate_credit_note_transition(old_status, target_reconciliation_status)

        credit_note.reconciliation_status = target_reconciliation_status

        hist_cnt = _get_max_counter(db, EntityStatusHistory.history_id, "HIST-2026-")
        sh = EntityStatusHistory(
            history_id=generate_status_history_id(hist_cnt),
            entity_name="CreditNote",
            entity_id=credit_note.credit_note_id,
            from_status=old_status.value if hasattr(old_status, "value") else str(old_status),
            to_status=target_reconciliation_status.value if hasattr(target_reconciliation_status, "value") else str(target_reconciliation_status),
            transition_reason=reason,
            changed_by=actor,
            changed_at=datetime.utcnow()
        )
        db.add(sh)

        ev_type = (
            AuditEventType.CREDIT_NOTE_RECONCILED
            if target_reconciliation_status in [CreditNoteReconciliationStatus.FULLY_APPLIED, CreditNoteReconciliationStatus.PARTIALLY_APPLIED]
            else AuditEventType.CREDIT_NOTE_REJECTED
        )

        payload = metadata or {}
        payload.update({
            "credit_note_number": credit_note.credit_note_number,
            "credit_amount": credit_note.credit_amount,
            "from_status": old_status.value if hasattr(old_status, "value") else str(old_status),
            "to_status": target_reconciliation_status.value if hasattr(target_reconciliation_status, "value") else str(target_reconciliation_status),
            "reason": reason
        })
        cls.record_audit_event(
            db=db,
            entity_type="CreditNote",
            entity_id=credit_note.credit_note_id,
            event_type=ev_type,
            actor=actor,
            payload=payload,
            notes=f"Credit Note {credit_note.credit_note_number} reconciliation: {target_reconciliation_status.value}"
        )

        db.flush()
        return credit_note

    @classmethod
    def record_manual_override(
        cls,
        db: Session,
        entity_type: str,
        entity_id: str,
        actor: str,
        override_reason: str,
        previous_decision: str,
        new_decision: str,
        financial_delta: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None
    ) -> AuditEvent:
        """
        Records an explicit, auditable manual override on an invoice or exception decision.
        """
        payload = metadata or {}
        payload.update({
            "previous_decision": previous_decision,
            "new_decision": new_decision,
            "override_reason": override_reason,
            "financial_delta": financial_delta
        })

        # Append to status history
        hist_cnt = _get_max_counter(db, EntityStatusHistory.history_id, "HIST-2026-")
        sh = EntityStatusHistory(
            history_id=generate_status_history_id(hist_cnt),
            entity_name=entity_type,
            entity_id=entity_id,
            from_status=previous_decision,
            to_status=new_decision,
            transition_reason=f"MANUAL OVERRIDE: {override_reason}",
            changed_by=actor,
            changed_at=datetime.utcnow()
        )
        db.add(sh)

        ev = cls.record_audit_event(
            db=db,
            entity_type=entity_type,
            entity_id=entity_id,
            event_type=AuditEventType.MANUAL_OVERRIDE_RECORDED,
            actor=actor,
            payload=payload,
            notes=f"Manual override applied by {actor}: {override_reason}"
        )
        db.flush()
        return ev
