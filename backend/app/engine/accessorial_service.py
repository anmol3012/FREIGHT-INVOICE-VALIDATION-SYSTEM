"""
Accessorial and Delivery Evidence Validation Service for Freight Invoice Validation System.
Validates accessorial fee entitlement, proof documents, dwell free-time rules,
and contractual fuel surcharge calculations.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session

from backend.app.models.accessorial import Accessorial, ShipmentAccessorial
from backend.app.models.shipment import Shipment, DeliveryEvidence
from backend.app.models.rate_card import RateCard
from backend.app.models.enums import AccessorialStatus, ChargeMethod


@dataclass
class AccessorialLineAuditResult:
    accessorial_code: str
    is_valid: bool
    expected_amount: float
    billed_amount: float
    variance_amount: float
    discrepancy_reason: Optional[str] = None
    requires_evidence: bool = False
    evidence_verified: bool = True
    evidence_document_ref: Optional[str] = None


@dataclass
class AccessorialAuditSummary:
    total_expected_accessorials: float
    total_expected_fuel_surcharge: float
    line_results: List[AccessorialLineAuditResult] = field(default_factory=list)
    has_unauthorized_charges: bool = False
    unauthorized_charges_count: int = 0


class AccessorialService:
    """
    Validates secondary and accessorial freight charges against operational evidence.
    """

    @classmethod
    def calculate_fuel_surcharge(
        cls, base_linehaul_amount: float, rate_card: Optional[RateCard], fsc_pct: float = 0.14
    ) -> float:
        """
        Fuel Surcharge is calculated as contractual percentage of base linehaul.
        """
        return round(base_linehaul_amount * fsc_pct, 2)

    @classmethod
    def audit_accessorial_charge(
        cls,
        db: Session,
        accessorial_code: str,
        billed_amount: float,
        billed_quantity: float,
        shipment: Optional[Shipment],
        delivery_evidence: Optional[DeliveryEvidence],
        rate_card: Optional[RateCard],
        linehaul_amount: float,
        chargeable_weight_kg: float
    ) -> AccessorialLineAuditResult:
        code = accessorial_code.strip().upper()

        # Look up definition in catalog
        acc = db.query(Accessorial).filter(
            Accessorial.accessorial_code == code,
            Accessorial.status == AccessorialStatus.ACTIVE
        ).first()

        if not acc:
            return AccessorialLineAuditResult(
                accessorial_code=code,
                is_valid=False,
                expected_amount=0.0,
                billed_amount=billed_amount,
                variance_amount=billed_amount,
                discrepancy_reason=f"Accessorial charge '{code}' is not recognized in active contractual catalog.",
                requires_evidence=False,
                evidence_verified=False
            )

        # Check date validity
        if shipment and shipment.ship_date:
            if shipment.ship_date < acc.effective_from or (acc.effective_to and shipment.ship_date > acc.effective_to):
                return AccessorialLineAuditResult(
                    accessorial_code=code,
                    is_valid=False,
                    expected_amount=0.0,
                    billed_amount=billed_amount,
                    variance_amount=billed_amount,
                    discrepancy_reason=f"Accessorial '{code}' is not effective on shipment date {shipment.ship_date.isoformat()}.",
                    requires_evidence=acc.requires_evidence,
                    evidence_verified=False
                )

        # Check operational shipment assignment
        sa_match = None
        if shipment and shipment.shipment_accessorials:
            for sa in shipment.shipment_accessorials:
                if sa.accessorial and sa.accessorial.accessorial_code.upper() == code:
                    sa_match = sa
                    break

        # Evidence verification rules
        evidence_verified = True
        evidence_doc = sa_match.evidence_reference if sa_match else None
        rejection_reason = None

        if acc.requires_evidence:
            if code == "LIFTGATE":
                # Entitled ONLY IF delivery evidence confirms liftgate was deployed
                liftgate_used = False
                if delivery_evidence and delivery_evidence.liftgate_actually_used:
                    liftgate_used = True
                    evidence_doc = delivery_evidence.signed_pod_ref or "POD-LIFTGATE-CONFIRMED"

                if not liftgate_used:
                    evidence_verified = False
                    rejection_reason = "Liftgate fee billed, but Delivery Evidence confirms facility has standard dock and liftgate was not utilized."

            elif code == "DETENTION":
                # Entitled ONLY IF recorded dwell exceeds free time (120 minutes)
                dwell_mins = delivery_evidence.detention_minutes_recorded if delivery_evidence else 0
                if dwell_mins <= 120:
                    evidence_verified = False
                    rejection_reason = f"Detention billed, but recorded facility dwell ({dwell_mins} min) is within standard 120 min free-time allowance."
                else:
                    evidence_doc = delivery_evidence.signed_pod_ref or f"GPS-ELD-LOG-{dwell_mins}MIN"

            else:
                # Other evidence-dependent accessorials
                if not sa_match or not sa_match.authorized:
                    evidence_verified = False
                    rejection_reason = f"Accessorial '{code}' requires pre-authorized operational proof, but none was recorded on shipment."

        if not evidence_verified:
            return AccessorialLineAuditResult(
                accessorial_code=code,
                is_valid=False,
                expected_amount=0.0,
                billed_amount=billed_amount,
                variance_amount=billed_amount,
                discrepancy_reason=rejection_reason,
                requires_evidence=True,
                evidence_verified=False,
                evidence_document_ref=evidence_doc
            )

        # Calculate expected contractual amount
        expected_amt = 0.0
        method = acc.charge_method
        if method == ChargeMethod.FLAT:
            expected_amt = round(acc.rate_amount * (billed_quantity or 1.0), 2)
        elif method == ChargeMethod.PER_KG:
            expected_amt = round(acc.rate_amount * chargeable_weight_kg, 2)
        elif method == ChargeMethod.PER_HOUR:
            if code == "DETENTION" and delivery_evidence:
                dwell_mins = delivery_evidence.detention_minutes_recorded or 0
                billable_hrs = max(0.0, round((dwell_mins - 120) / 60.0, 2))
                expected_amt = round(acc.rate_amount * billable_hrs, 2)
            else:
                expected_amt = round(acc.rate_amount * (billed_quantity or 1.0), 2)
        elif method == ChargeMethod.PERCENTAGE:
            expected_amt = round(linehaul_amount * (acc.rate_amount / 100.0), 2)
        else:
            expected_amt = round(acc.rate_amount, 2)

        variance = round(billed_amount - expected_amt, 2)
        is_valid = abs(variance) <= 0.05 # tolerance

        return AccessorialLineAuditResult(
            accessorial_code=code,
            is_valid=is_valid,
            expected_amount=expected_amt,
            billed_amount=billed_amount,
            variance_amount=variance,
            discrepancy_reason=f"Billed amount ${billed_amount:.2f} differs from contractual expected ${expected_amt:.2f}." if not is_valid else None,
            requires_evidence=acc.requires_evidence,
            evidence_verified=True,
            evidence_document_ref=evidence_doc
        )
