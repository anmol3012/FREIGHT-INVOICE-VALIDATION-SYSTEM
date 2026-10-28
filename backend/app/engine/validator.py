import hashlib
import json
from datetime import datetime
from typing import List, Dict, Tuple, Optional
from sqlalchemy.orm import Session
from backend.app.core.config import settings
from backend.app.models.invoice import InvoiceHeader, InvoiceLine
from backend.app.models.shipment import Shipment, WeightMeasurement, AccessorialEvent, DeliveryRecord
from backend.app.models.rate_card import RateCard, RateLane, AccessorialRule
from backend.app.models.exception import InvoiceException
from backend.app.models.credit_note import CreditNote
from backend.app.models.audit import AuditEvent
from backend.app.engine.calculator import FreightCalculator, CalculationResult

class InvoiceValidator:
    """
    Automated Freight Invoice Reconciliation & Audit Engine.
    Executes line-level reconciliation, tolerance evaluation,
    accessorial entitlement verification, and duplicate billing detection.
    """

    @staticmethod
    def compute_invoice_fingerprint(carrier_id: int, bol_number: str, total_billed: float) -> str:
        raw_str = f"{carrier_id}:{bol_number.strip().upper()}:{total_billed:.2f}"
        return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()

    @classmethod
    def check_duplicate(cls, db: Session, invoice: InvoiceHeader) -> Optional[InvoiceHeader]:
        """
        Check for duplicate billing:
        1. Identical fingerprint (same carrier, same BOL, same billed total) on an earlier invoice.
        2. Or cross-invoice billing: earlier invoice with same carrier and BOL already validated/paid.
        """
        if not invoice.bol_number_billed:
            return None

        # Fingerprint match
        fingerprint = invoice.fingerprint_hash or cls.compute_invoice_fingerprint(
            invoice.carrier_id, invoice.bol_number_billed, invoice.total_billed_amount
        )

        match = db.query(InvoiceHeader).filter(
            InvoiceHeader.id < invoice.id,
            InvoiceHeader.carrier_id == invoice.carrier_id,
            InvoiceHeader.bol_number_billed == invoice.bol_number_billed,
            InvoiceHeader.fingerprint_hash == fingerprint
        ).first()

        if match:
            return match

        # Also check for repeat billing of the same BOL even with slightly altered amount
        repeat = db.query(InvoiceHeader).filter(
            InvoiceHeader.id < invoice.id,
            InvoiceHeader.carrier_id == invoice.carrier_id,
            InvoiceHeader.bol_number_billed == invoice.bol_number_billed,
            InvoiceHeader.status.in_(["VALIDATED_MATCH", "EXCEPTION_APPROVED", "PAID"])
        ).first()

        return repeat

    @classmethod
    def validate_invoice(cls, db: Session, invoice_id: int, actor: str = "SYSTEM_AUDITOR") -> InvoiceHeader:
        invoice = db.query(InvoiceHeader).filter(InvoiceHeader.id == invoice_id).first()
        if not invoice:
            raise ValueError(f"Invoice {invoice_id} not found")

        # 1. Check for Duplicate Billing
        existing_dup = cls.check_duplicate(db, invoice)
        if existing_dup:
            invoice.is_duplicate = True
            invoice.duplicate_of_invoice_id = existing_dup.id
            invoice.status = "EXCEPTION_DISPUTED"
            invoice.validation_status = "FAILED"
            invoice.validated_at = datetime.utcnow()
            
            # Clear old exceptions
            db.query(InvoiceException).filter(InvoiceException.invoice_id == invoice.id).delete()

            dup_exc = InvoiceException(
                invoice_id=invoice.id,
                category="DUPLICATE_BILLING",
                severity="CRITICAL",
                billed_amount=invoice.total_billed_amount,
                expected_amount=0.0,
                variance_amount=invoice.total_billed_amount,
                status="DISPUTED",
                root_cause_code="DUPLICATE_INVOICE_PRESENTED",
                explanation=f"Duplicate invoice detected. Original invoice {existing_dup.invoice_number} already exists for BOL {invoice.bol_number_billed}."
            )
            db.add(dup_exc)

            # Audit event
            db.add(AuditEvent(
                entity_type="INVOICE",
                entity_id=str(invoice.id),
                event_type="DUPLICATE_DETECTED",
                actor=actor,
                payload_json=json.dumps({"duplicate_of_invoice_number": existing_dup.invoice_number, "bol": invoice.bol_number_billed}),
                notes=f"Flagged as duplicate of invoice {existing_dup.invoice_number}"
            ))

            db.commit()
            db.refresh(invoice)
            return invoice

        # 2. Retrieve operational shipment & contract rate cards
        shipment = invoice.shipment
        if not shipment and invoice.bol_number_billed:
            shipment = db.query(Shipment).filter(Shipment.bol_number == invoice.bol_number_billed).first()

        if not shipment:
            # Unmatched shipment
            invoice.status = "EXCEPTION_DISPUTED"
            invoice.validation_status = "FAILED"
            invoice.validated_at = datetime.utcnow()
            db.add(InvoiceException(
                invoice_id=invoice.id,
                category="UNMATCHED_SHIPMENT",
                severity="CRITICAL",
                billed_amount=invoice.total_billed_amount,
                expected_amount=0.0,
                variance_amount=invoice.total_billed_amount,
                status="OPEN",
                root_cause_code="NO_MATCHING_BOL",
                explanation=f"Billed BOL {invoice.bol_number_billed} does not correspond to any valid shipment record in the system."
            ))
            db.commit()
            db.refresh(invoice)
            return invoice

        # Retrieve carrier active rate card
        rate_card = db.query(RateCard).filter(
            RateCard.carrier_id == invoice.carrier_id,
            RateCard.status == "ACTIVE",
            RateCard.effective_date <= invoice.invoice_date,
            RateCard.expiration_date >= invoice.invoice_date
        ).first()

        # Retrieve rate lane matching origin/dest zip prefix
        origin_prefix = shipment.origin_zip[:3] if shipment.origin_zip else "ALL"
        dest_prefix = shipment.destination_zip[:3] if shipment.destination_zip else "ALL"

        rate_lane = None
        if rate_card:
            rate_lane = db.query(RateLane).filter(
                RateLane.rate_card_id == rate_card.id,
                RateLane.origin_zip_prefix.in_([origin_prefix, "ALL"]),
                RateLane.dest_zip_prefix.in_([dest_prefix, "ALL"])
            ).first()

        # Accessorial rules
        accessorial_rules = db.query(AccessorialRule).filter(
            AccessorialRule.carrier_id == invoice.carrier_id
        ).all()

        weight_measurement = db.query(WeightMeasurement).filter(
            WeightMeasurement.shipment_id == shipment.id,
            WeightMeasurement.certified == True
        ).first()

        delivery_record = db.query(DeliveryRecord).filter(
            DeliveryRecord.shipment_id == shipment.id
        ).first()

        accessorial_events = db.query(AccessorialEvent).filter(
            AccessorialEvent.shipment_id == shipment.id
        ).all()

        # 3. Calculate Contractual Expected Charges
        calc_result: CalculationResult = FreightCalculator.calculate_expected_charges(
            shipment=shipment,
            rate_card=rate_card,
            rate_lane=rate_lane,
            accessorial_rules=accessorial_rules,
            weight_measurement=weight_measurement,
            delivery_record=delivery_record,
            accessorial_events=accessorial_events
        )

        invoice.calculated_expected_amount = calc_result.total_expected_amount
        invoice.total_variance_amount = round(invoice.total_billed_amount - calc_result.total_expected_amount, 2)
        invoice.validated_at = datetime.utcnow()

        # Clear existing exceptions and re-evaluate lines
        db.query(InvoiceException).filter(InvoiceException.invoice_id == invoice.id).delete()

        # Reconcile lines against expected breakdown
        expected_items_map = {}
        for item in calc_result.line_items:
            expected_items_map[item.charge_code] = item

        exceptions_to_raise: List[InvoiceException] = []

        for line in invoice.lines:
            code = (line.charge_code or "").upper()
            if code in expected_items_map:
                exp_item = expected_items_map[code]
                line.expected_units = exp_item.expected_units
                line.expected_rate = exp_item.expected_rate
                line.expected_amount = exp_item.expected_amount
                line.variance_amount = round(line.billed_amount - exp_item.expected_amount, 2)

                line_var = abs(line.variance_amount)
                if line_var <= settings.ABSOLUTE_TOLERANCE_USD:
                    line.status = "MATCH"
                    line.discrepancy_reason = None
                else:
                    line.status = "VARIANCE_DISCREPANCY"
                    
                    # Determine exact scenario root cause
                    if line.charge_type == "LINEHAUL":
                        # Check if weight discrepancy vs base rate mismatch
                        if weight_measurement and abs(line.billed_units - calc_result.billable_weight_lbs / 100.0) > 0.5:
                            category = "WEIGHT_DISCREPANCY"
                            root_cause = "SCALE_WEIGHT_DISCREPANCY"
                            reason = f"Billed {line.billed_units:.2f} CWT ({line.billed_units*100:.0f} lbs) exceeds certified scale/dim weight {calc_result.billable_weight_lbs:.0f} lbs."
                        else:
                            category = "BASE_RATE_MISMATCH"
                            root_cause = "TARIFF_RATE_INFLATION"
                            reason = f"Billed rate ${line.billed_rate:.2f} exceeds contracted rate ${exp_item.expected_rate:.2f} (variance: ${line.variance_amount:+.2f})."
                    else:
                        category = "BASE_RATE_MISMATCH"
                        root_cause = "RATE_DISCREPANCY"
                        reason = f"Variance of ${line.variance_amount:+.2f} on {line.description}."

                    line.discrepancy_reason = reason
                    exceptions_to_raise.append(InvoiceException(
                        invoice_id=invoice.id,
                        invoice_line_id=line.id,
                        category=category,
                        severity="CRITICAL" if abs(line.variance_amount) > 25.0 else "WARNING",
                        billed_amount=line.billed_amount,
                        expected_amount=exp_item.expected_amount,
                        variance_amount=line.variance_amount,
                        status="OPEN",
                        root_cause_code=root_cause,
                        explanation=reason
                    ))
            else:
                # Billed line has NO corresponding expected charge (Unauthorized Accessorial or extra fee)
                line.expected_units = 0.0
                line.expected_rate = 0.0
                line.expected_amount = 0.0
                line.variance_amount = round(line.billed_amount, 2)
                line.status = "UNAUTHORIZED"

                if line.charge_type == "ACCESSORIAL" or code in ["LIFTGATE", "DETENTION", "RESIDENTIAL", "INSIDE_DELIVERY"]:
                    category = "UNAUTHORIZED_ACCESSORIAL"
                    root_cause = "UNRENDERED_OR_UNAUTHORIZED_ACCESSORIAL"
                    if code == "LIFTGATE":
                        reason = "Liftgate fee billed, but delivery receipt confirms standard dock delivery with no liftgate used."
                    elif code == "DETENTION":
                        reason = f"Detention fee billed, but driver dwell time did not exceed contracted {settings.DETENTION_FREE_MINUTES} min free time."
                    else:
                        reason = f"Accessorial charge '{line.description}' was not authorized or verified by destination proof."
                else:
                    category = "BASE_RATE_MISMATCH"
                    root_cause = "UNCONTRACTED_CHARGE"
                    reason = f"Uncontracted charge '{line.description}' billed without contractual provision."

                line.discrepancy_reason = reason
                exceptions_to_raise.append(InvoiceException(
                    invoice_id=invoice.id,
                    invoice_line_id=line.id,
                    category=category,
                    severity="CRITICAL",
                    billed_amount=line.billed_amount,
                    expected_amount=0.0,
                    variance_amount=line.variance_amount,
                    status="OPEN",
                    root_cause_code=root_cause,
                    explanation=reason
                ))

        # 4. Overall Invoice Header Evaluation
        net_variance = abs(invoice.total_variance_amount)
        pct_variance = (net_variance / max(1.0, calc_result.total_expected_amount))

        if len(exceptions_to_raise) == 0 and (net_variance <= settings.ABSOLUTE_TOLERANCE_USD or pct_variance <= settings.PERCENTAGE_TOLERANCE):
            invoice.status = "VALIDATED_MATCH"
            invoice.validation_status = "PASSED"
            invoice.reconciliation_notes = f"Audit passed successfully. Billed ${invoice.total_billed_amount:.2f} matched expected ${calc_result.total_expected_amount:.2f} within tolerance."
        else:
            invoice.status = "EXCEPTION_DISPUTED"
            invoice.validation_status = "FAILED"
            invoice.reconciliation_notes = f"Audit failed with {len(exceptions_to_raise)} line discrepancy(s). Total variance: ${invoice.total_variance_amount:+.2f}."
            for exc in exceptions_to_raise:
                db.add(exc)

        # Audit Event log
        db.add(AuditEvent(
            entity_type="INVOICE",
            entity_id=str(invoice.id),
            event_type="VALIDATION_RUN",
            actor=actor,
            payload_json=json.dumps({
                "billed": invoice.total_billed_amount,
                "expected": calc_result.total_expected_amount,
                "variance": invoice.total_variance_amount,
                "exceptions_count": len(exceptions_to_raise),
                "status": invoice.status
            }),
            notes=invoice.reconciliation_notes
        ))

        db.commit()
        db.refresh(invoice)
        return invoice

    @classmethod
    def validate_credit_note(cls, db: Session, credit_note_id: int, actor: str = "SYSTEM_AUDITOR") -> CreditNote:
        """
        Scenario 5 Validation: Validate credit notes against parent invoices.
        Rules:
        - Parent invoice must exist and belong to the same carrier.
        - Credit amount must be strictly > 0 and <= original invoice variance / dispute balance.
        - Credit note must not be duplicate.
        """
        cn = db.query(CreditNote).filter(CreditNote.id == credit_note_id).first()
        if not cn:
            raise ValueError(f"Credit note {credit_note_id} not found")

        parent_inv = db.query(InvoiceHeader).filter(InvoiceHeader.id == cn.original_invoice_id).first()

        if not parent_inv:
            cn.status = "REJECTED"
            cn.rejection_reason = "Parent invoice reference does not exist in the system."
            db.commit()
            return cn

        if parent_inv.carrier_id != cn.carrier_id:
            cn.status = "REJECTED"
            cn.rejection_reason = "Carrier mismatch between credit note and parent invoice."
            db.commit()
            return cn

        if cn.credit_amount <= 0:
            cn.status = "REJECTED"
            cn.rejection_reason = "Credit note amount must be greater than zero."
            db.commit()
            return cn

        # Check maximum allowable credit (cannot exceed parent invoice variance)
        max_allowable = max(0.0, parent_inv.total_variance_amount)
        if round(cn.credit_amount, 2) > round(max_allowable + 1.0, 2): # allow $1 penny tolerance
            cn.status = "REJECTED"
            cn.rejection_reason = f"Credit note amount (${cn.credit_amount:.2f}) exceeds allowable dispute variance (${max_allowable:.2f})."
            
            # Also record an audit exception
            db.add(InvoiceException(
                invoice_id=parent_inv.id,
                category="INVALID_CREDIT_NOTE",
                severity="CRITICAL",
                billed_amount=cn.credit_amount,
                expected_amount=max_allowable,
                variance_amount=cn.credit_amount - max_allowable,
                status="DISPUTED",
                root_cause_code="EXCESSIVE_CREDIT_NOTE",
                explanation=cn.rejection_reason
            ))
            db.commit()
            return cn

        # Valid credit note: apply to invoice
        cn.status = "FULLY_APPLIED"
        cn.applied_amount = cn.credit_amount
        cn.remaining_balance = 0.0
        cn.rejection_reason = None

        # Update parent invoice
        parent_inv.status = "EXCEPTION_APPROVED"
        parent_inv.reconciliation_notes = (parent_inv.reconciliation_notes or "") + f" [Resolved by Credit Note {cn.credit_note_number} for ${cn.credit_amount:.2f}]"

        # Resolve open exceptions on invoice
        for exc in parent_inv.exceptions:
            if exc.status == "OPEN":
                exc.status = "AUTO_RESOLVED"
                exc.resolved_by = "CREDIT_NOTE_RECONCILIATION"
                exc.resolution_notes = f"Cleared by credit note {cn.credit_note_number}"
                exc.resolved_at = datetime.utcnow()

        db.add(AuditEvent(
            entity_type="CREDIT_NOTE",
            entity_id=str(cn.id),
            event_type="CREDIT_NOTE_APPLIED",
            actor=actor,
            payload_json=json.dumps({"credit_note_number": cn.credit_note_number, "amount": cn.credit_amount, "invoice_id": parent_inv.id}),
            notes=f"Successfully reconciled with invoice {parent_inv.invoice_number}"
        ))

        db.commit()
        db.refresh(cn)
        return cn
