"""
Lifecycle State Machine and Transition Rules.
Enforces valid state progressions for Shipments, Invoices, Exceptions, and Credit Notes.
"""

from typing import Dict, Set
from backend.app.models.enums import (
    ShipmentStatus, InvoiceStatus, ExceptionStatus, CreditNoteReconciliationStatus
)

class InvalidStateTransitionError(ValueError):
    """Raised when an illegal lifecycle transition is attempted."""
    pass

# Permitted state transitions
SHIPMENT_TRANSITIONS: Dict[ShipmentStatus, Set[ShipmentStatus]] = {
    ShipmentStatus.BOOKED: {ShipmentStatus.IN_TRANSIT, ShipmentStatus.CANCELLED},
    ShipmentStatus.IN_TRANSIT: {ShipmentStatus.OUT_FOR_DELIVERY, ShipmentStatus.DELIVERED, ShipmentStatus.EXCEPTION, ShipmentStatus.CANCELLED},
    ShipmentStatus.OUT_FOR_DELIVERY: {ShipmentStatus.DELIVERED, ShipmentStatus.EXCEPTION},
    ShipmentStatus.EXCEPTION: {ShipmentStatus.IN_TRANSIT, ShipmentStatus.OUT_FOR_DELIVERY, ShipmentStatus.DELIVERED, ShipmentStatus.CANCELLED},
    ShipmentStatus.DELIVERED: set(),  # Terminal state
    ShipmentStatus.CANCELLED: set(),  # Terminal state
}

INVOICE_TRANSITIONS: Dict[InvoiceStatus, Set[InvoiceStatus]] = {
    InvoiceStatus.SUBMITTED: {InvoiceStatus.PENDING_AUDIT, InvoiceStatus.CANCELLED},
    InvoiceStatus.PENDING_AUDIT: {InvoiceStatus.VALIDATED_MATCH, InvoiceStatus.EXCEPTION_DISPUTED, InvoiceStatus.REJECTED, InvoiceStatus.CANCELLED},
    InvoiceStatus.VALIDATED_MATCH: {InvoiceStatus.PAID, InvoiceStatus.EXCEPTION_DISPUTED, InvoiceStatus.CANCELLED},
    InvoiceStatus.EXCEPTION_DISPUTED: {InvoiceStatus.EXCEPTION_APPROVED, InvoiceStatus.REJECTED, InvoiceStatus.CANCELLED},
    InvoiceStatus.EXCEPTION_APPROVED: {InvoiceStatus.PAID, InvoiceStatus.CANCELLED},
    InvoiceStatus.PAID: set(),      # Terminal state
    InvoiceStatus.REJECTED: set(),  # Terminal state
    InvoiceStatus.CANCELLED: set(), # Terminal state
}

EXCEPTION_TRANSITIONS: Dict[ExceptionStatus, Set[ExceptionStatus]] = {
    ExceptionStatus.OPEN: {ExceptionStatus.UNDER_REVIEW, ExceptionStatus.DISPUTED, ExceptionStatus.APPROVED_OVERRIDE, ExceptionStatus.AUTO_RESOLVED, ExceptionStatus.REJECTED},
    ExceptionStatus.UNDER_REVIEW: {ExceptionStatus.DISPUTED, ExceptionStatus.APPROVED_OVERRIDE, ExceptionStatus.AUTO_RESOLVED, ExceptionStatus.REJECTED},
    ExceptionStatus.DISPUTED: {ExceptionStatus.AUTO_RESOLVED, ExceptionStatus.APPROVED_OVERRIDE, ExceptionStatus.REJECTED},
    ExceptionStatus.APPROVED_OVERRIDE: set(), # Terminal
    ExceptionStatus.AUTO_RESOLVED: set(),     # Terminal
    ExceptionStatus.REJECTED: set(),          # Terminal
}

CREDIT_NOTE_TRANSITIONS: Dict[CreditNoteReconciliationStatus, Set[CreditNoteReconciliationStatus]] = {
    CreditNoteReconciliationStatus.UNAPPLIED: {CreditNoteReconciliationStatus.PARTIALLY_APPLIED, CreditNoteReconciliationStatus.FULLY_APPLIED, CreditNoteReconciliationStatus.REJECTED},
    CreditNoteReconciliationStatus.PARTIALLY_APPLIED: {CreditNoteReconciliationStatus.FULLY_APPLIED, CreditNoteReconciliationStatus.REJECTED},
    CreditNoteReconciliationStatus.FULLY_APPLIED: set(),
    CreditNoteReconciliationStatus.REJECTED: set(),
}

def validate_shipment_transition(current: ShipmentStatus, target: ShipmentStatus) -> bool:
    if current == target:
        return True
    allowed = SHIPMENT_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise InvalidStateTransitionError(f"Cannot transition Shipment from '{current.value}' to '{target.value}'. Allowed: {[s.value for s in allowed]}")
    return True

def validate_invoice_transition(current: InvoiceStatus, target: InvoiceStatus) -> bool:
    if current == target:
        return True
    allowed = INVOICE_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise InvalidStateTransitionError(f"Cannot transition FreightInvoice from '{current.value}' to '{target.value}'. Allowed: {[s.value for s in allowed]}")
    return True

def validate_exception_transition(current: ExceptionStatus, target: ExceptionStatus) -> bool:
    if current == target:
        return True
    allowed = EXCEPTION_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise InvalidStateTransitionError(f"Cannot transition AuditException from '{current.value}' to '{target.value}'. Allowed: {[s.value for s in allowed]}")
    return True

def validate_credit_note_transition(current: CreditNoteReconciliationStatus, target: CreditNoteReconciliationStatus) -> bool:
    if current == target:
        return True
    allowed = CREDIT_NOTE_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise InvalidStateTransitionError(f"Cannot transition CreditNote from '{current.value}' to '{target.value}'. Allowed: {[s.value for s in allowed]}")
    return True
