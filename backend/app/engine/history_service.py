"""
Historical Traceability and Audit Inspection Service.
Provides end-to-end lineage, chronological lifecycle transitions,
and rule-based explanations for any invoice, exception, or carrier.
"""

from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from backend.app.models.invoice import FreightInvoice, InvoiceLine, InvoiceValidationRun
from backend.app.models.audit_exception import AuditException
from backend.app.models.credit_note import CreditNote
from backend.app.models.audit import AuditEvent, EntityStatusHistory
from backend.app.models.shipment import Shipment, DeliveryEvidence, WeightMeasurement


class HistoryService:
    """
    Assembles complete historical lineage and audit trails for freight invoices.
    """

    @classmethod
    def get_invoice_traceability(cls, db: Session, invoice_id: str) -> Dict[str, Any]:
        invoice = db.query(FreightInvoice).filter(FreightInvoice.invoice_id == invoice_id).first()
        if not invoice:
            raise ValueError(f"Freight invoice '{invoice_id}' not found.")

        # 1. Invoice Lines & Line Variances
        lines_data = []
        for line in sorted(invoice.invoice_lines, key=lambda l: l.line_number):
            lines_data.append({
                "line_id": line.invoice_line_id,
                "line_number": line.line_number,
                "line_type": line.line_type.value if hasattr(line.line_type, "value") else str(line.line_type),
                "description": line.description,
                "quantity": line.quantity,
                "unit_of_measure": line.unit_of_measure,
                "unit_rate": line.unit_rate,
                "billed_amount": line.billed_amount,
                "expected_amount": line.expected_amount,
                "variance_amount": line.variance_amount,
                "evidence_reference": line.evidence_reference,
                "source_reference": line.source_reference
            })

        # 2. Associated Shipment & Evidence
        shipment_data = None
        if invoice.shipment:
            s = invoice.shipment
            dev = s.delivery_evidence
            shipment_data = {
                "shipment_id": s.shipment_id,
                "carrier_id": s.carrier_id,
                "lane_id": s.lane_id,
                "service_level": s.service_level.value,
                "ship_date": s.ship_date.isoformat(),
                "delivery_due_date": s.delivery_due_date.isoformat(),
                "delivered_at": s.delivered_at.isoformat() if s.delivered_at else None,
                "actual_weight_kg": s.actual_weight_kg,
                "chargeable_weight_kg": s.chargeable_weight_kg,
                "dimensions_cm": {
                    "length": s.actual_length_cm,
                    "width": s.actual_width_cm,
                    "height": s.actual_height_cm
                },
                "delivery_evidence": {
                    "recipient_name": dev.recipient_name if dev else None,
                    "signed_pod_ref": dev.signed_pod_ref if dev else None,
                    "facility_dock_type": dev.facility_dock_type if dev else None,
                    "liftgate_actually_used": dev.liftgate_actually_used if dev else False,
                    "detention_minutes": dev.detention_minutes_recorded if dev else 0
                } if dev else None
            }

        # 3. Exceptions
        exceptions_data = []
        for exc in invoice.audit_exceptions:
            exceptions_data.append({
                "exception_id": exc.exception_id,
                "exception_type": exc.exception_type.value,
                "severity": exc.severity.value,
                "billed_amount": exc.billed_amount,
                "expected_amount": exc.expected_amount,
                "disputed_amount": exc.disputed_amount,
                "explanation": exc.explanation,
                "exception_status": exc.exception_status.value,
                "detected_at": exc.detected_at.isoformat(),
                "resolved_at": exc.resolved_at.isoformat() if exc.resolved_at else None
            })

        # 4. Credit Notes
        credit_notes_data = []
        for cn in invoice.credit_notes:
            credit_notes_data.append({
                "credit_note_id": cn.credit_note_id,
                "credit_note_number": cn.credit_note_number,
                "issue_date": cn.issue_date.isoformat(),
                "credit_amount": cn.credit_amount,
                "approval_status": cn.approval_status.value,
                "reconciliation_status": cn.reconciliation_status.value
            })

        # 5. Validation Runs
        runs_data = []
        for vr in invoice.validation_runs:
            runs_data.append({
                "validation_run_id": vr.validation_run_id,
                "run_at": vr.run_at.isoformat(),
                "actor": vr.actor,
                "rules_applied_count": vr.rules_applied_count,
                "exceptions_detected_count": vr.exceptions_detected_count,
                "summary_verdict": vr.summary_verdict
            })

        # 6. Entity Status History (Lifecycle Progression)
        status_histories = db.query(EntityStatusHistory).filter(
            EntityStatusHistory.entity_id == invoice.invoice_id
        ).order_by(EntityStatusHistory.changed_at.asc()).all()

        history_timeline = [{
            "history_id": sh.history_id,
            "from_status": sh.from_status,
            "to_status": sh.to_status,
            "transition_reason": sh.transition_reason,
            "changed_by": sh.changed_by,
            "changed_at": sh.changed_at.isoformat()
        } for sh in status_histories]

        # 7. Immutable Audit Events
        audit_events = db.query(AuditEvent).filter(
            AuditEvent.entity_id == invoice.invoice_id
        ).order_by(AuditEvent.timestamp.asc()).all()

        events_timeline = [{
            "event_id": ev.event_id,
            "event_type": ev.event_type,
            "actor": ev.actor,
            "notes": ev.notes,
            "timestamp": ev.timestamp.isoformat()
        } for ev in audit_events]

        return {
            "invoice": {
                "invoice_id": invoice.invoice_id,
                "carrier_id": invoice.carrier_id,
                "invoice_number": invoice.invoice_number,
                "raw_shipment_reference": invoice.raw_shipment_reference,
                "invoice_date": invoice.invoice_date.isoformat(),
                "due_date": invoice.due_date.isoformat(),
                "currency": invoice.currency,
                "billed_total": invoice.billed_total,
                "expected_total": invoice.expected_total,
                "variance_amount": invoice.variance_amount,
                "invoice_status": invoice.invoice_status.value,
                "validation_status": invoice.validation_status.value,
                "reference_rejection_reason": invoice.reference_rejection_reason
            },
            "shipment": shipment_data,
            "lines": lines_data,
            "exceptions": exceptions_data,
            "credit_notes": credit_notes_data,
            "validation_runs": runs_data,
            "lifecycle_transitions": history_timeline,
            "audit_events": events_timeline
        }
