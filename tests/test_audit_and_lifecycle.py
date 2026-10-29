"""
Phase 4 Automated Tests: Auditability and Lifecycle State Transitions.
Verifies immutable audit logging, state machine progression,
rejection of invalid transitions without state corruption, and manual override tracking.
"""

import pytest
from datetime import date, datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.core.database import Base
from backend.app.models.enums import (
    CarrierStatus, InvoiceStatus, ExceptionStatus, CreditNoteReconciliationStatus,
    CreditNoteApprovalStatus, AuditEventType
)
from backend.app.models.carrier import Carrier
from backend.app.models.invoice import FreightInvoice
from backend.app.models.audit_exception import AuditException
from backend.app.models.credit_note import CreditNote
from backend.app.models.audit import AuditEvent, EntityStatusHistory
from backend.app.models.lifecycle import InvalidStateTransitionError
from backend.app.engine.audit_service import AuditService


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)
    db = TestingSession()
    yield db
    db.close()


@pytest.fixture
def sample_entities(test_db):
    carrier = Carrier(
        carrier_id="CAR-000001",
        carrier_name="Swift Freight",
        carrier_code="SWFT",
        status=CarrierStatus.ACTIVE
    )
    test_db.add(carrier)

    invoice = FreightInvoice(
        invoice_id="FINV-2026-000001",
        carrier_id="CAR-000001",
        raw_shipment_reference="SHP-2026-000001",
        invoice_number="INV-001",
        invoice_date=date(2026, 4, 1),
        service_period_start=date(2026, 4, 1),
        service_period_end=date(2026, 4, 3),
        due_date=date(2026, 5, 1),
        billed_total=500.0,
        invoice_status=InvoiceStatus.SUBMITTED
    )
    test_db.add(invoice)

    exception = AuditException(
        exception_id="FEX-2026-000001",
        invoice_id="FINV-2026-000001",
        exception_type="BASE_RATE_MISMATCH",
        severity="HIGH",
        expected_amount=400.0,
        billed_amount=500.0,
        disputed_amount=100.0,
        explanation="Tariff discrepancy",
        exception_status=ExceptionStatus.OPEN
    )
    test_db.add(exception)

    credit_note = CreditNote(
        credit_note_id="CN-2026-000001",
        exception_id="FEX-2026-000001",
        invoice_id="FINV-2026-000001",
        carrier_id="CAR-000001",
        credit_note_number="CN-001",
        issue_date=date(2026, 4, 10),
        credit_amount=100.0,
        approval_status=CreditNoteApprovalStatus.PENDING_APPROVAL,
        reconciliation_status=CreditNoteReconciliationStatus.UNAPPLIED
    )
    test_db.add(credit_note)

    test_db.commit()
    return {
        "invoice": invoice,
        "exception": exception,
        "credit_note": credit_note
    }


def test_valid_invoice_lifecycle_progression(test_db, sample_entities):
    """Verifies that legal invoice state transitions are recorded in history and audit events."""
    inv = sample_entities["invoice"]

    # SUBMITTED -> PENDING_AUDIT
    AuditService.transition_invoice(
        db=test_db,
        invoice=inv,
        target_status=InvoiceStatus.PENDING_AUDIT,
        reason="Invoice queued for automated audit engine",
        actor="INGESTION_WORKER"
    )
    assert inv.invoice_status == InvoiceStatus.PENDING_AUDIT

    # PENDING_AUDIT -> EXCEPTION_DISPUTED
    AuditService.transition_invoice(
        db=test_db,
        invoice=inv,
        target_status=InvoiceStatus.EXCEPTION_DISPUTED,
        reason="Discrepancy detected by audit rules",
        actor="AUDIT_ENGINE"
    )
    assert inv.invoice_status == InvoiceStatus.EXCEPTION_DISPUTED

    # Verify history and events were persisted
    histories = test_db.query(EntityStatusHistory).filter(EntityStatusHistory.entity_id == inv.invoice_id).all()
    assert len(histories) == 2
    assert histories[0].from_status == "SUBMITTED"
    assert histories[0].to_status == "PENDING_AUDIT"
    assert histories[1].from_status == "PENDING_AUDIT"
    assert histories[1].to_status == "EXCEPTION_DISPUTED"

    events = test_db.query(AuditEvent).filter(AuditEvent.entity_id == inv.invoice_id).all()
    assert len(events) == 2
    assert all(e.event_type == AuditEventType.INVOICE_STATUS_CHANGED.value for e in events)


def test_invalid_invoice_lifecycle_transition_rejected(test_db, sample_entities):
    """
    Verifies that an illegal transition (e.g. SUBMITTED -> PAID directly)
    raises InvalidStateTransitionError and preserves current state without corruption.
    """
    inv = sample_entities["invoice"]
    assert inv.invoice_status == InvoiceStatus.SUBMITTED

    with pytest.raises(InvalidStateTransitionError):
        AuditService.transition_invoice(
            db=test_db,
            invoice=inv,
            target_status=InvoiceStatus.PAID, # Illegal skip of validation
            reason="Illegal jump to paid",
            actor="ROGUE_ACTOR"
        )

    # State must remain SUBMITTED, uncorrupted
    assert inv.invoice_status == InvoiceStatus.SUBMITTED

    # No status history or audit event recorded
    hist_count = test_db.query(EntityStatusHistory).filter(EntityStatusHistory.entity_id == inv.invoice_id).count()
    assert hist_count == 0


def test_exception_lifecycle_progression(test_db, sample_entities):
    """Tests progression: OPEN -> UNDER_REVIEW -> DISPUTED -> AUTO_RESOLVED."""
    exc = sample_entities["exception"]

    # OPEN -> UNDER_REVIEW
    AuditService.transition_exception(
        db=test_db,
        exception=exc,
        target_status=ExceptionStatus.UNDER_REVIEW,
        reason="Assigned to logistics analyst",
        actor="ANALYST_ALICE"
    )
    assert exc.exception_status == ExceptionStatus.UNDER_REVIEW

    # UNDER_REVIEW -> DISPUTED
    AuditService.transition_exception(
        db=test_db,
        exception=exc,
        target_status=ExceptionStatus.DISPUTED,
        reason="Dispute notice transmitted to carrier",
        actor="DISPUTE_TEAM"
    )
    assert exc.exception_status == ExceptionStatus.DISPUTED

    # DISPUTED -> AUTO_RESOLVED
    AuditService.transition_exception(
        db=test_db,
        exception=exc,
        target_status=ExceptionStatus.AUTO_RESOLVED,
        reason="Credit note applied in full",
        actor="RECONCILIATION_ENGINE"
    )
    assert exc.exception_status == ExceptionStatus.AUTO_RESOLVED
    assert exc.resolved_at is not None


def test_manual_override_recording(test_db, sample_entities):
    """Verifies that an analyst manual override is explicitly recorded with audit diff metadata."""
    inv = sample_entities["invoice"]

    override_ev = AuditService.record_manual_override(
        db=test_db,
        entity_type="FreightInvoice",
        entity_id=inv.invoice_id,
        actor="SENIOR_AUDITOR_BOB",
        override_reason="Commercial concession approved by VP Logistics",
        previous_decision="EXCEPTION_DISPUTED",
        new_decision="APPROVED_OVERRIDE",
        financial_delta=-100.0,
        metadata={"concession_ref": "VP-APPROVAL-4029"}
    )

    assert override_ev is not None
    assert override_ev.event_type == AuditEventType.MANUAL_OVERRIDE_RECORDED.value
    assert override_ev.actor == "SENIOR_AUDITOR_BOB"
    assert "Commercial concession" in override_ev.notes

    # Verify history entry created
    hist = test_db.query(EntityStatusHistory).filter(
        EntityStatusHistory.entity_id == inv.invoice_id
    ).first()
    assert hist is not None
    assert "MANUAL OVERRIDE" in hist.transition_reason
