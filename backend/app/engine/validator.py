"""
Comprehensive 20-Step Freight Invoice Calculation & Validation Engine.
Performs deterministic line-level reconciliation, contract rate verification,
evidence proof auditing, duplicate detection, exception creation,
and explainable decision logging.
"""

import json
from datetime import datetime, date, timedelta
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session

from backend.app.models.enums import (
    InvoiceStatus, ValidationStatus, ExceptionType, ExceptionSeverity, ExceptionStatus,
    CreditNoteApprovalStatus, CreditNoteReconciliationStatus, RateCardStatus
)
from backend.app.models.carrier import Carrier
from backend.app.models.lane import Lane
from backend.app.models.rate_card import RateCard
from backend.app.models.shipment import Shipment, DeliveryEvidence
from backend.app.models.invoice import FreightInvoice, InvoiceLine, InvoiceValidationRun
from backend.app.models.audit_exception import AuditException
from backend.app.models.credit_note import CreditNote
from backend.app.models.audit import AuditEvent, EntityStatusHistory
from backend.app.models.id_generator import (
    generate_exception_id, generate_validation_run_id,
    generate_audit_event_id, generate_status_history_id
)
from backend.app.engine.contract_selector import ContractSelector, RateCardSelectionResult
from backend.app.engine.weight_service import WeightRatingService, WeightEvaluationResult
from backend.app.engine.accessorial_service import AccessorialService, AccessorialLineAuditResult
from backend.app.engine.duplicate_service import DuplicateDetectionService, DuplicateCheckResult
from backend.app.engine.credit_note_service import CreditNoteService


def _get_max_counter(db: Session, model_col, prefix: str) -> int:
    """Helper to safely determine highest zero-padded sequence ID in DB."""
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


@dataclass
class InvoiceValidationSummary:
    invoice_id: str
    overall_verdict: str # "PASSED", "FAILED", "REVIEW_REQUIRED"
    validation_status: ValidationStatus
    invoice_status: InvoiceStatus
    billed_total: float
    expected_total: float
    variance_amount: float # billed - expected
    exceptions_raised_count: int
    exception_ids: List[str] = field(default_factory=list)
    line_results: List[Dict[str, Any]] = field(default_factory=list)
    diagnostic_messages: List[str] = field(default_factory=list)


class FreightInvoiceValidator:
    """
    Production-grade Freight Invoice Validation Engine implementing the 20-step workflow.
    """

    @classmethod
    def validate_invoice(
        cls,
        db: Session,
        invoice_id: str,
        actor: str = "SYSTEM_AUDITOR",
        tolerance_amount: float = 0.50
    ) -> InvoiceValidationSummary:
        invoice = db.query(FreightInvoice).filter(FreightInvoice.invoice_id == invoice_id).first()
        if not invoice:
            raise ValueError(f"Freight invoice '{invoice_id}' not found.")

        diagnostics: List[str] = []
        exceptions_to_create: List[Dict[str, Any]] = []
        line_audit_results: List[Dict[str, Any]] = []

        # -------------------------------------------------------------
        # Step 1: Validate invoice structure and required fields
        # -------------------------------------------------------------
        lines: List[InvoiceLine] = sorted(invoice.invoice_lines, key=lambda l: l.line_number) if invoice.invoice_lines else []
        if lines:
            line_sum = round(sum(l.billed_amount for l in lines), 2)
            if abs(line_sum - round(invoice.billed_total, 2)) > 0.05:
                # Header does not reconcile with itemized lines
                exceptions_to_create.append({
                    "line_id": None,
                    "type": ExceptionType.CALCULATION_ERROR,
                    "severity": ExceptionSeverity.HIGH,
                    "expected": line_sum,
                    "billed": invoice.billed_total,
                    "disputed": round(invoice.billed_total - line_sum, 2),
                    "explanation": f"Header billed total (${invoice.billed_total:.2f}) does not match sum of itemized lines (${line_sum:.2f})."
                })
                diagnostics.append("Invoice line sum mismatch with header total.")

        # -------------------------------------------------------------
        # Step 2: Resolve the carrier
        # -------------------------------------------------------------
        carrier = db.query(Carrier).filter(Carrier.carrier_id == invoice.carrier_id).first()
        if not carrier:
            exceptions_to_create.append({
                "line_id": None,
                "type": ExceptionType.CALCULATION_ERROR,
                "severity": ExceptionSeverity.CRITICAL,
                "expected": 0.0,
                "billed": invoice.billed_total,
                "disputed": invoice.billed_total,
                "explanation": f"Carrier '{invoice.carrier_id}' does not exist in master records."
            })
            return cls._finalize_failure(db, invoice, exceptions_to_create, diagnostics, actor, "UNRESOLVED_CARRIER")

        # -------------------------------------------------------------
        # Step 3: Resolve shipment reference (Scenario A Check)
        # -------------------------------------------------------------
        shipment = None
        if invoice.shipment_id:
            shipment = db.query(Shipment).filter(Shipment.shipment_id == invoice.shipment_id).first()

        # If shipment_id was null or not found, try lookup by raw_shipment_reference
        if not shipment and invoice.raw_shipment_reference:
            shipment = db.query(Shipment).filter(
                Shipment.shipment_id == invoice.raw_shipment_reference
            ).first()

        if not shipment:
            # Scenario A: Unknown shipment reference!
            invoice.reference_rejection_reason = "Raw shipment reference does not exist in master operational records"
            exceptions_to_create.append({
                "line_id": None,
                "type": ExceptionType.UNMATCHED_SHIPMENT,
                "severity": ExceptionSeverity.CRITICAL,
                "expected": 0.0,
                "billed": invoice.billed_total,
                "disputed": invoice.billed_total,
                "explanation": f"Scenario A: Shipment reference '{invoice.raw_shipment_reference}' cannot be matched to any operational shipment record."
            })
            diagnostics.append(f"Shipment reference '{invoice.raw_shipment_reference}' is unknown.")
            return cls._finalize_failure(db, invoice, exceptions_to_create, diagnostics, actor, "UNKNOWN_SHIPMENT_REF")

        # -------------------------------------------------------------
        # Step 4: Verify carrier-shipment relationship
        # -------------------------------------------------------------
        if shipment.carrier_id != carrier.carrier_id:
            exceptions_to_create.append({
                "line_id": None,
                "type": ExceptionType.UNMATCHED_SHIPMENT,
                "severity": ExceptionSeverity.CRITICAL,
                "expected": 0.0,
                "billed": invoice.billed_total,
                "disputed": invoice.billed_total,
                "explanation": f"Carrier mismatch: Invoice carrier {carrier.carrier_id} did not perform shipment {shipment.shipment_id} (assigned to {shipment.carrier_id})."
            })
            diagnostics.append("Carrier does not match shipment performer.")

        # -------------------------------------------------------------
        # Step 5: Resolve the lane
        # -------------------------------------------------------------
        lane = db.query(Lane).filter(Lane.lane_id == shipment.lane_id).first()
        if not lane:
            diagnostics.append(f"Lane '{shipment.lane_id}' not found.")

        # -------------------------------------------------------------
        # Steps 6, 7, 8: Resolve rate card, effective dates & service level (Scenario B Check)
        # -------------------------------------------------------------
        contract_result: RateCardSelectionResult = ContractSelector.select_rate_card(
            db=db,
            carrier_id=carrier.carrier_id,
            lane_id=shipment.lane_id,
            service_level=shipment.service_level,
            shipment_date=shipment.ship_date
        )

        rate_card = contract_result.rate_card

        if contract_result.status == "EXPIRED":
            # Scenario B: Referenced / selected rate card has expired
            exceptions_to_create.append({
                "line_id": None,
                "type": ExceptionType.BASE_RATE_MISMATCH,
                "severity": ExceptionSeverity.CRITICAL,
                "expected": 0.0,
                "billed": invoice.billed_total,
                "disputed": invoice.billed_total,
                "explanation": f"Scenario B: {contract_result.reason}"
            })
            diagnostics.append(contract_result.reason)

        elif contract_result.status == "MISSING":
            exceptions_to_create.append({
                "line_id": None,
                "type": ExceptionType.BASE_RATE_MISMATCH,
                "severity": ExceptionSeverity.CRITICAL,
                "expected": 0.0,
                "billed": invoice.billed_total,
                "disputed": invoice.billed_total,
                "explanation": contract_result.reason
            })
            diagnostics.append(contract_result.reason)

        # -------------------------------------------------------------
        # Steps 9, 10, 11, 12: Weight, tiers & base linehaul (Scenarios C & F Check)
        # -------------------------------------------------------------
        weight_result: WeightEvaluationResult = WeightRatingService.evaluate_shipment_weight(
            shipment=shipment,
            rate_card=rate_card
        )

        expected_linehaul = weight_result.expected_linehaul_amount

        # -------------------------------------------------------------
        # Step 13, 14: Fuel surcharge, accessorials & delivery evidence (Scenario G Check)
        # -------------------------------------------------------------
        delivery_evidence = db.query(DeliveryEvidence).filter(
            DeliveryEvidence.shipment_id == shipment.shipment_id
        ).first()

        expected_fsc = AccessorialService.calculate_fuel_surcharge(expected_linehaul, rate_card)

        # -------------------------------------------------------------
        # Step 15: Reconcile each invoice line
        # -------------------------------------------------------------
        total_calculated_expected = 0.0
        seen_line_types = set()

        for line in lines:
            l_type = line.line_type.value if hasattr(line.line_type, "value") else str(line.line_type)
            line_expected = 0.0
            line_explanation = None

            if l_type == "BASE_LINEHAUL":
                line_expected = expected_linehaul

                # Check weight discrepancy (Scenario F)
                if abs(line.quantity - weight_result.chargeable_weight_kg) > 2.0:
                    disputed_wt = round(line.billed_amount - line_expected, 2)
                    if disputed_wt > tolerance_amount:
                        exceptions_to_create.append({
                            "line_id": line.invoice_line_id,
                            "type": ExceptionType.WEIGHT_DISCREPANCY,
                            "severity": ExceptionSeverity.HIGH,
                            "expected": line_expected,
                            "billed": line.billed_amount,
                            "disputed": disputed_wt,
                            "explanation": f"Scenario F: Dimensional/Scale weight discrepancy on line {line.line_number}. Billed on {line.quantity:.1f} kg, but certified chargeable weight is {weight_result.chargeable_weight_kg:.1f} kg."
                        })

                # Check tier misclassification (Scenario C)
                elif weight_result.matched_tier and abs(line.unit_rate - weight_result.tier_rate_per_kg) > 0.005:
                    disputed_rate = round(line.billed_amount - line_expected, 2)
                    if disputed_rate > tolerance_amount:
                        exceptions_to_create.append({
                            "line_id": line.invoice_line_id,
                            "type": ExceptionType.WEIGHT_DISCREPANCY,
                            "severity": ExceptionSeverity.HIGH,
                            "expected": line_expected,
                            "billed": line.billed_amount,
                            "disputed": disputed_rate,
                            "explanation": f"Scenario C: Incorrect weight tier billed on line {line.line_number}. Applied rate ${line.unit_rate:.4f}/kg does not match contracted Tier {weight_result.tier_sequence} rate ${weight_result.tier_rate_per_kg:.4f}/kg."
                        })

                # General base rate variance
                elif (line.billed_amount - line_expected) > tolerance_amount:
                    disputed_amt = round(line.billed_amount - line_expected, 2)
                    exceptions_to_create.append({
                        "line_id": line.invoice_line_id,
                        "type": ExceptionType.BASE_RATE_MISMATCH,
                        "severity": ExceptionSeverity.HIGH,
                        "expected": line_expected,
                        "billed": line.billed_amount,
                        "disputed": disputed_amt,
                        "explanation": f"Base linehaul rate discrepancy on line {line.line_number}: Billed ${line.billed_amount:.2f} vs expected ${line_expected:.2f}."
                    })

            elif l_type == "FUEL_SURCHARGE":
                if "FUEL_SURCHARGE" in seen_line_types:
                    # Scenario D: Duplicate fuel surcharge line!
                    line_expected = 0.0
                    exceptions_to_create.append({
                        "line_id": line.invoice_line_id,
                        "type": ExceptionType.DUPLICATE_BILLING,
                        "severity": ExceptionSeverity.CRITICAL,
                        "expected": 0.0,
                        "billed": line.billed_amount,
                        "disputed": line.billed_amount,
                        "explanation": f"Scenario D: Duplicate fuel surcharge billed on line {line.line_number} (${line.billed_amount:.2f})."
                    })
                else:
                    line_expected = expected_fsc
                    if (line.billed_amount - line_expected) > tolerance_amount:
                        exceptions_to_create.append({
                            "line_id": line.invoice_line_id,
                            "type": ExceptionType.CALCULATION_ERROR,
                            "severity": ExceptionSeverity.MEDIUM,
                            "expected": line_expected,
                            "billed": line.billed_amount,
                            "disputed": round(line.billed_amount - line_expected, 2),
                            "explanation": f"Fuel surcharge calculation discrepancy on line {line.line_number}: Billed ${line.billed_amount:.2f} vs expected ${line_expected:.2f}."
                        })

            elif l_type == "ACCESSORIAL":
                # Scenario G Check
                acc_code = line.description.split()[0].upper()
                audit_acc = AccessorialService.audit_accessorial_charge(
                    db=db,
                    accessorial_code=acc_code,
                    billed_amount=line.billed_amount,
                    billed_quantity=line.quantity,
                    shipment=shipment,
                    delivery_evidence=delivery_evidence,
                    rate_card=rate_card,
                    linehaul_amount=expected_linehaul,
                    chargeable_weight_kg=weight_result.chargeable_weight_kg
                )
                line_expected = audit_acc.expected_amount

                if not audit_acc.is_valid and audit_acc.variance_amount > tolerance_amount:
                    exceptions_to_create.append({
                        "line_id": line.invoice_line_id,
                        "type": ExceptionType.UNAUTHORIZED_ACCESSORIAL,
                        "severity": ExceptionSeverity.HIGH,
                        "expected": line_expected,
                        "billed": line.billed_amount,
                        "disputed": audit_acc.variance_amount,
                        "explanation": f"Scenario G: {audit_acc.discrepancy_reason}"
                    })

            # Update line reconciliation fields
            line_var = round(line.billed_amount - line_expected, 2)
            line.expected_amount = line_expected
            line.variance_amount = line_var
            total_calculated_expected += line_expected
            seen_line_types.add(l_type)

            line_audit_results.append({
                "line_id": line.invoice_line_id,
                "line_number": line.line_number,
                "line_type": l_type,
                "billed_amount": line.billed_amount,
                "expected_amount": line_expected,
                "variance_amount": line_var
            })

        # -------------------------------------------------------------
        # Step 16: Reconcile invoice total
        # -------------------------------------------------------------
        total_calculated_expected = round(total_calculated_expected, 2)
        total_variance = round(invoice.billed_total - total_calculated_expected, 2)
        invoice.expected_total = total_calculated_expected
        invoice.variance_amount = total_variance

        # -------------------------------------------------------------
        # Step 17: Duplicate billing detection (Scenario H & Line D)
        # -------------------------------------------------------------
        dup_result: DuplicateCheckResult = DuplicateDetectionService.check_invoice_duplicate(db, invoice)
        if dup_result.is_duplicate:
            exceptions_to_create.append({
                "line_id": None,
                "type": ExceptionType.DUPLICATE_BILLING,
                "severity": ExceptionSeverity.CRITICAL,
                "expected": 0.0,
                "billed": invoice.billed_total,
                "disputed": invoice.billed_total,
                "explanation": f"Scenario H: {dup_result.explanation}"
            })
            diagnostics.append(dup_result.explanation)

        # -------------------------------------------------------------
        # Step 18: Create explainable exceptions
        # -------------------------------------------------------------
        created_exception_ids = []
        # Clear previous open exceptions for this invoice to prevent duplicate tickets on re-audit
        db.query(AuditException).filter(
            AuditException.invoice_id == invoice.invoice_id,
            AuditException.exception_status.in_([ExceptionStatus.OPEN, ExceptionStatus.UNDER_REVIEW])
        ).delete()
        db.flush()

        base_counter = _get_max_counter(db, AuditException.exception_id, "FEX-2026-")
        for idx, exc_data in enumerate(exceptions_to_create, start=base_counter):
            exc_id = generate_exception_id(idx)
            exc = AuditException(
                exception_id=exc_id,
                invoice_id=invoice.invoice_id,
                invoice_line_id=exc_data.get("line_id"),
                shipment_id=shipment.shipment_id if shipment else None,
                exception_type=exc_data["type"],
                severity=exc_data["severity"],
                expected_amount=exc_data["expected"],
                billed_amount=exc_data["billed"],
                disputed_amount=exc_data["disputed"],
                currency=invoice.currency,
                explanation=exc_data["explanation"],
                evidence_json=json.dumps({
                    "raw_shipment_ref": invoice.raw_shipment_reference,
                    "carrier_id": carrier.carrier_id,
                    "billed_total": invoice.billed_total,
                    "calculated_expected": total_calculated_expected
                }),
                exception_status=ExceptionStatus.OPEN,
                detected_at=datetime.utcnow()
            )
            db.add(exc)
            created_exception_ids.append(exc_id)

        # -------------------------------------------------------------
        # Step 19: Validate linked credit notes (Scenario E Check)
        # -------------------------------------------------------------
        linked_credit_notes = db.query(CreditNote).filter(
            CreditNote.invoice_id == invoice.invoice_id
        ).all()
        for cn in linked_credit_notes:
            cn_audit = CreditNoteService.validate_credit_note(db, cn.credit_note_id)
            if not cn_audit.is_valid:
                diagnostics.append(cn_audit.explanation)

        # -------------------------------------------------------------
        # Step 20: Store validation result and audit events
        # -------------------------------------------------------------
        has_exceptions = len(exceptions_to_create) > 0
        overall_verdict = "FAILED" if has_exceptions else "PASSED"
        invoice.validation_status = ValidationStatus.FAILED if has_exceptions else ValidationStatus.PASSED
        invoice.invoice_status = InvoiceStatus.EXCEPTION_DISPUTED if has_exceptions else InvoiceStatus.VALIDATED_MATCH

        vrun_count = _get_max_counter(db, InvoiceValidationRun.validation_run_id, "VRUN-2026-")
        vrun = InvoiceValidationRun(
            validation_run_id=generate_validation_run_id(vrun_count),
            invoice_id=invoice.invoice_id,
            run_at=datetime.utcnow(),
            actor=actor,
            rules_applied_count=20,
            exceptions_detected_count=len(exceptions_to_create),
            summary_verdict=overall_verdict,
            details_json=json.dumps({
                "verdict": overall_verdict,
                "exceptions_count": len(exceptions_to_create),
                "billed_total": invoice.billed_total,
                "expected_total": total_calculated_expected,
                "variance": total_variance,
                "diagnostics": diagnostics
            })
        )
        db.add(vrun)

        # Audit Event log
        ev_count = _get_max_counter(db, AuditEvent.event_id, "AUD-2026-")
        db.add(AuditEvent(
            event_id=generate_audit_event_id(ev_count),
            entity_type="FreightInvoice",
            entity_id=invoice.invoice_id,
            event_type="VALIDATION_EXECUTED",
            actor=actor,
            payload_json=json.dumps({
                "verdict": overall_verdict,
                "exceptions_raised": len(exceptions_to_create),
                "variance": total_variance
            }),
            notes=f"Audit completed: {overall_verdict} (Variance: ${total_variance:,.2f})",
            timestamp=datetime.utcnow()
        ))

        db.commit()

        return InvoiceValidationSummary(
            invoice_id=invoice.invoice_id,
            overall_verdict=overall_verdict,
            validation_status=invoice.validation_status,
            invoice_status=invoice.invoice_status,
            billed_total=invoice.billed_total,
            expected_total=total_calculated_expected,
            variance_amount=total_variance,
            exceptions_raised_count=len(exceptions_to_create),
            exception_ids=created_exception_ids,
            line_results=line_audit_results,
            diagnostic_messages=diagnostics
        )

    @classmethod
    def _finalize_failure(
        cls,
        db: Session,
        invoice: FreightInvoice,
        exceptions: List[Dict[str, Any]],
        diagnostics: List[str],
        actor: str,
        reason_code: str
    ) -> InvoiceValidationSummary:
        invoice.validation_status = ValidationStatus.FAILED
        invoice.invoice_status = InvoiceStatus.EXCEPTION_DISPUTED
        invoice.expected_total = 0.0
        invoice.variance_amount = invoice.billed_total

        # Clear existing open exceptions
        db.query(AuditException).filter(
            AuditException.invoice_id == invoice.invoice_id,
            AuditException.exception_status == ExceptionStatus.OPEN
        ).delete()
        db.flush()

        created_ids = []
        base_counter = _get_max_counter(db, AuditException.exception_id, "FEX-2026-")
        for idx, exc_data in enumerate(exceptions, start=base_counter):
            exc_id = generate_exception_id(idx)
            exc = AuditException(
                exception_id=exc_id,
                invoice_id=invoice.invoice_id,
                invoice_line_id=exc_data.get("line_id"),
                shipment_id=None,
                exception_type=exc_data["type"],
                severity=exc_data["severity"],
                expected_amount=exc_data["expected"],
                billed_amount=exc_data["billed"],
                disputed_amount=exc_data["disputed"],
                currency=invoice.currency,
                explanation=exc_data["explanation"],
                evidence_json=json.dumps({"reason_code": reason_code, "raw_ref": invoice.raw_shipment_reference}),
                exception_status=ExceptionStatus.OPEN,
                detected_at=datetime.utcnow()
            )
            db.add(exc)
            created_ids.append(exc_id)

        vrun_count = _get_max_counter(db, InvoiceValidationRun.validation_run_id, "VRUN-2026-")
        db.add(InvoiceValidationRun(
            validation_run_id=generate_validation_run_id(vrun_count),
            invoice_id=invoice.invoice_id,
            run_at=datetime.utcnow(),
            actor=actor,
            rules_applied_count=3,
            exceptions_detected_count=len(exceptions),
            summary_verdict="FAILED",
            details_json=json.dumps({"failure_reason": reason_code, "diagnostics": diagnostics})
        ))

        db.commit()

        return InvoiceValidationSummary(
            invoice_id=invoice.invoice_id,
            overall_verdict="FAILED",
            validation_status=invoice.validation_status,
            invoice_status=invoice.invoice_status,
            billed_total=invoice.billed_total,
            expected_total=0.0,
            variance_amount=invoice.billed_total,
            exceptions_raised_count=len(exceptions),
            exception_ids=created_ids,
            line_results=[],
            diagnostic_messages=diagnostics
        )


# Backward compatibility alias
InvoiceValidator = FreightInvoiceValidator
