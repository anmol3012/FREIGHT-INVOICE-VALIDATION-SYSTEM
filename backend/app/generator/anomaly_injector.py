"""
Dedicated Anomaly Injection Engine for Synthetic Data Generation.
Injects explicitly labelled anomalies (A, B, C, D, E, plus dimensional, duplicates, accessorials).
Preserves ground-truth metadata in isolated GroundTruthLabel records.
"""

import json
from dataclasses import dataclass
from typing import Dict, Any, List, Optional
from datetime import date, timedelta
from backend.app.models.enums import (
    InvoiceStatus, ValidationStatus, InvoiceLineType, ExceptionType
)
from backend.app.models.id_generator import generate_anomaly_id

@dataclass
class AnomalyInjectionResult:
    issue_type: str
    is_anomaly: bool
    expected_decision: str # PASS or FAIL
    raw_shipment_ref: str
    shipment_id: Optional[str]
    reference_rejection_reason: Optional[str]
    injected_lines: List[Dict[str, Any]]
    total_billed: float
    ground_truth_expected: float
    injected_variance: float
    anomaly_id: Optional[str]
    injection_method: str
    affected_entity_ids: List[str]
    details: Dict[str, Any]


class AnomalyInjector:
    """
    Applies deterministic anomalies to baseline invoice lines and records ground truth.
    """

    @classmethod
    def apply_anomaly(
        cls,
        issue_type: str,
        counter: int,
        invoice_id: str,
        shipment,
        rate_card,
        baseline_calc,
        carrier,
        rng
    ) -> AnomalyInjectionResult:
        """
        Takes a valid baseline calculation and mutates lines/references according to issue_type.
        """
        anomaly_id = generate_anomaly_id(counter) if issue_type != "NORMAL" else None
        lines = []
        injected_variance = 0.0
        affected_ids = [invoice_id]
        if shipment:
            affected_ids.append(shipment.shipment_id)
        if rate_card:
            affected_ids.append(rate_card.rate_card_id)

        # -------------------------------------------------------------
        # Baseline Normal: Perfect contractual match
        # -------------------------------------------------------------
        if issue_type == "NORMAL":
            for idx, item in enumerate(baseline_calc.charge_items):
                lines.append({
                    "line_number": idx + 1,
                    "line_type": item.charge_type,
                    "accessorial_id": item.accessorial_id,
                    "description": item.description,
                    "quantity": item.quantity,
                    "unit_of_measure": item.unit_of_measure,
                    "unit_rate": item.unit_rate,
                    "billed_amount": item.expected_amount,
                    "expected_amount": item.expected_amount,
                    "variance_amount": 0.0,
                    "evidence_reference": item.evidence_reference,
                    "source_reference": item.source_reference
                })
            return AnomalyInjectionResult(
                issue_type="NORMAL",
                is_anomaly=False,
                expected_decision="PASS",
                raw_shipment_ref=shipment.shipment_id,
                shipment_id=shipment.shipment_id,
                reference_rejection_reason=None,
                injected_lines=lines,
                total_billed=baseline_calc.total_expected_amount,
                ground_truth_expected=baseline_calc.total_expected_amount,
                injected_variance=0.0,
                anomaly_id=None,
                injection_method="BASELINE_VALID",
                affected_entity_ids=affected_ids,
                details={"status": "Clean baseline matching contract"}
            )

        # -------------------------------------------------------------
        # Anomaly A: Unknown Shipment Reference (Untrusted External Ref)
        # -------------------------------------------------------------
        elif issue_type == "UNKNOWN_SHIPMENT_REF":
            bogus_ref = f"SHP-UNKNOWN-{rng.randint(700000, 999999)}"
            for idx, item in enumerate(baseline_calc.charge_items):
                lines.append({
                    "line_number": idx + 1,
                    "line_type": item.charge_type,
                    "accessorial_id": item.accessorial_id,
                    "description": item.description,
                    "quantity": item.quantity,
                    "unit_of_measure": item.unit_of_measure,
                    "unit_rate": item.unit_rate,
                    "billed_amount": item.expected_amount,
                    "expected_amount": 0.0, # Cannot calculate expected without valid shipment
                    "variance_amount": item.expected_amount,
                    "evidence_reference": item.evidence_reference,
                    "source_reference": item.source_reference
                })
            total_billed = baseline_calc.total_expected_amount
            return AnomalyInjectionResult(
                issue_type=issue_type,
                is_anomaly=True,
                expected_decision="FAIL",
                raw_shipment_ref=bogus_ref,
                shipment_id=None, # Persist NULL to preserve DB FK integrity!
                reference_rejection_reason="Raw shipment reference does not exist in master operational records",
                injected_lines=lines,
                total_billed=total_billed,
                ground_truth_expected=0.0,
                injected_variance=total_billed,
                anomaly_id=anomaly_id,
                injection_method="UNTRUSTED_SHIPMENT_REF_STAGING",
                affected_entity_ids=affected_ids,
                details={"fictitious_ref": bogus_ref}
            )

        # -------------------------------------------------------------
        # Anomaly B: Expired Rate Card (Obsolete Tariff Applied)
        # -------------------------------------------------------------
        elif issue_type == "EXPIRED_RATE_CARD":
            markup_pct = round(rng.uniform(0.20, 0.35), 2) # 20% - 35% tariff inflation
            for idx, item in enumerate(baseline_calc.charge_items):
                if item.charge_type == "BASE_LINEHAUL":
                    inflated_rate = round(item.unit_rate * (1.0 + markup_pct), 4)
                    inflated_amt = round(item.quantity * inflated_rate, 2)
                    var = round(inflated_amt - item.expected_amount, 2)
                    injected_variance += var
                    lines.append({
                        "line_number": idx + 1,
                        "line_type": item.charge_type,
                        "accessorial_id": None,
                        "description": f"Linehaul Base (Billed on Expired Tariff Schedule +{markup_pct*100:.0f}%)",
                        "quantity": item.quantity,
                        "unit_of_measure": item.unit_of_measure,
                        "unit_rate": inflated_rate,
                        "billed_amount": inflated_amt,
                        "expected_amount": item.expected_amount,
                        "variance_amount": var,
                        "evidence_reference": item.evidence_reference,
                        "source_reference": f"EXPIRED-{rate_card.rate_card_id if rate_card else 'TARIFF'}"
                    })
                else:
                    lines.append({
                        "line_number": idx + 1,
                        "line_type": item.charge_type,
                        "accessorial_id": item.accessorial_id,
                        "description": item.description,
                        "quantity": item.quantity,
                        "unit_of_measure": item.unit_of_measure,
                        "unit_rate": item.unit_rate,
                        "billed_amount": item.expected_amount,
                        "expected_amount": item.expected_amount,
                        "variance_amount": 0.0,
                        "evidence_reference": item.evidence_reference,
                        "source_reference": item.source_reference
                    })
            total_billed = round(baseline_calc.total_expected_amount + injected_variance, 2)
            return AnomalyInjectionResult(
                issue_type=issue_type,
                is_anomaly=True,
                expected_decision="FAIL",
                raw_shipment_ref=shipment.shipment_id,
                shipment_id=shipment.shipment_id,
                reference_rejection_reason=None,
                injected_lines=lines,
                total_billed=total_billed,
                ground_truth_expected=baseline_calc.total_expected_amount,
                injected_variance=injected_variance,
                anomaly_id=anomaly_id,
                injection_method="TARIFF_RATE_INFLATION_EXPIRED_SCHEDULE",
                affected_entity_ids=affected_ids,
                details={"markup_pct": markup_pct, "contracted_rate": baseline_calc.charge_items[0].unit_rate}
            )

        # -------------------------------------------------------------
        # Anomaly C: Incorrect Weight Tier (Higher Tier Rate Billed)
        # -------------------------------------------------------------
        elif issue_type == "INCORRECT_WEIGHT_TIER":
            # Overcharge by bumping tier rate to Tier 1 pricing
            tier_markup = round(rng.uniform(0.15, 0.30), 2)
            for idx, item in enumerate(baseline_calc.charge_items):
                if item.charge_type == "BASE_LINEHAUL":
                    wrong_tier_rate = round(item.unit_rate * (1.0 + tier_markup), 4)
                    inflated_amt = round(item.quantity * wrong_tier_rate, 2)
                    var = round(inflated_amt - item.expected_amount, 2)
                    injected_variance += var
                    lines.append({
                        "line_number": idx + 1,
                        "line_type": item.charge_type,
                        "accessorial_id": None,
                        "description": f"Linehaul Base (Misclassified Weight Tier Bracket)",
                        "quantity": item.quantity,
                        "unit_of_measure": item.unit_of_measure,
                        "unit_rate": wrong_tier_rate,
                        "billed_amount": inflated_amt,
                        "expected_amount": item.expected_amount,
                        "variance_amount": var,
                        "evidence_reference": item.evidence_reference,
                        "source_reference": item.source_reference
                    })
                else:
                    lines.append({
                        "line_number": idx + 1,
                        "line_type": item.charge_type,
                        "accessorial_id": item.accessorial_id,
                        "description": item.description,
                        "quantity": item.quantity,
                        "unit_of_measure": item.unit_of_measure,
                        "unit_rate": item.unit_rate,
                        "billed_amount": item.expected_amount,
                        "expected_amount": item.expected_amount,
                        "variance_amount": 0.0,
                        "evidence_reference": item.evidence_reference,
                        "source_reference": item.source_reference
                    })
            total_billed = round(baseline_calc.total_expected_amount + injected_variance, 2)
            return AnomalyInjectionResult(
                issue_type=issue_type,
                is_anomaly=True,
                expected_decision="FAIL",
                raw_shipment_ref=shipment.shipment_id,
                shipment_id=shipment.shipment_id,
                reference_rejection_reason=None,
                injected_lines=lines,
                total_billed=total_billed,
                ground_truth_expected=baseline_calc.total_expected_amount,
                injected_variance=injected_variance,
                anomaly_id=anomaly_id,
                injection_method="WEIGHT_TIER_MISCLASSIFICATION",
                affected_entity_ids=affected_ids,
                details={"tier_markup_pct": tier_markup}
            )

        # -------------------------------------------------------------
        # Anomaly D: Duplicate Fuel Surcharge
        # -------------------------------------------------------------
        elif issue_type == "DUPLICATE_FUEL_SURCHARGE":
            fsc_extra = round(baseline_calc.fuel_surcharge_amount or 45.0, 2)
            injected_variance = fsc_extra

            for idx, item in enumerate(baseline_calc.charge_items):
                lines.append({
                    "line_number": idx + 1,
                    "line_type": item.charge_type,
                    "accessorial_id": item.accessorial_id,
                    "description": item.description,
                    "quantity": item.quantity,
                    "unit_of_measure": item.unit_of_measure,
                    "unit_rate": item.unit_rate,
                    "billed_amount": item.expected_amount,
                    "expected_amount": item.expected_amount,
                    "variance_amount": 0.0,
                    "evidence_reference": item.evidence_reference,
                    "source_reference": item.source_reference
                })

            # Append second duplicate fuel surcharge line
            lines.append({
                "line_number": len(lines) + 1,
                "line_type": "FUEL_SURCHARGE",
                "accessorial_id": None,
                "description": "Secondary Fuel Adjustment Surcharge (Duplicate Assessment)",
                "quantity": 1.0,
                "unit_of_measure": "FLAT",
                "unit_rate": fsc_extra,
                "billed_amount": fsc_extra,
                "expected_amount": 0.0, # Expected is 0!
                "variance_amount": fsc_extra,
                "evidence_reference": None,
                "source_reference": "ERRONEOUS_DOUBLE_FSC"
            })
            total_billed = round(baseline_calc.total_expected_amount + fsc_extra, 2)
            return AnomalyInjectionResult(
                issue_type=issue_type,
                is_anomaly=True,
                expected_decision="FAIL",
                raw_shipment_ref=shipment.shipment_id,
                shipment_id=shipment.shipment_id,
                reference_rejection_reason=None,
                injected_lines=lines,
                total_billed=total_billed,
                ground_truth_expected=baseline_calc.total_expected_amount,
                injected_variance=injected_variance,
                anomaly_id=anomaly_id,
                injection_method="DUPLICATE_FUEL_SURCHARGE_LINE",
                affected_entity_ids=affected_ids,
                details={"duplicate_fsc_amount": fsc_extra}
            )

        # -------------------------------------------------------------
        # Anomaly F: Dimensional Weight Calculation Discrepancy
        # -------------------------------------------------------------
        elif issue_type == "DIMENSIONAL_WEIGHT_DISCREPANCY":
            # Inflate billed weight by 35% - 60%
            wt_mult = round(rng.uniform(1.35, 1.60), 2)
            for idx, item in enumerate(baseline_calc.charge_items):
                if item.charge_type == "BASE_LINEHAUL":
                    inflated_qty = round(item.quantity * wt_mult, 1)
                    inflated_amt = round(inflated_qty * item.unit_rate, 2)
                    var = round(inflated_amt - item.expected_amount, 2)
                    injected_variance += var
                    lines.append({
                        "line_number": idx + 1,
                        "line_type": item.charge_type,
                        "accessorial_id": None,
                        "description": f"Linehaul Base (Inflated Volumetric Density)",
                        "quantity": inflated_qty,
                        "unit_of_measure": item.unit_of_measure,
                        "unit_rate": item.unit_rate,
                        "billed_amount": inflated_amt,
                        "expected_amount": item.expected_amount,
                        "variance_amount": var,
                        "evidence_reference": item.evidence_reference,
                        "source_reference": item.source_reference
                    })
                else:
                    lines.append({
                        "line_number": idx + 1,
                        "line_type": item.charge_type,
                        "accessorial_id": item.accessorial_id,
                        "description": item.description,
                        "quantity": item.quantity,
                        "unit_of_measure": item.unit_of_measure,
                        "unit_rate": item.unit_rate,
                        "billed_amount": item.expected_amount,
                        "expected_amount": item.expected_amount,
                        "variance_amount": 0.0,
                        "evidence_reference": item.evidence_reference,
                        "source_reference": item.source_reference
                    })
            total_billed = round(baseline_calc.total_expected_amount + injected_variance, 2)
            return AnomalyInjectionResult(
                issue_type=issue_type,
                is_anomaly=True,
                expected_decision="FAIL",
                raw_shipment_ref=shipment.shipment_id,
                shipment_id=shipment.shipment_id,
                reference_rejection_reason=None,
                injected_lines=lines,
                total_billed=total_billed,
                ground_truth_expected=baseline_calc.total_expected_amount,
                injected_variance=injected_variance,
                anomaly_id=anomaly_id,
                injection_method="DIM_WEIGHT_INFLATION",
                affected_entity_ids=affected_ids,
                details={"weight_multiplier": wt_mult, "certified_chargeable_kg": baseline_calc.chargeable_weight_kg}
            )

        # -------------------------------------------------------------
        # Anomaly H: Unauthorized / Unrendered Accessorial
        # -------------------------------------------------------------
        elif issue_type == "UNAUTHORIZED_ACCESSORIAL":
            unauth_code = rng.choice(["LIFTGATE", "DETENTION", "INSIDE_DELIVERY"])
            fee = 85.0 if unauth_code == "LIFTGATE" else (150.0 if unauth_code == "DETENTION" else 75.0)
            injected_variance = fee

            for idx, item in enumerate(baseline_calc.charge_items):
                lines.append({
                    "line_number": idx + 1,
                    "line_type": item.charge_type,
                    "accessorial_id": item.accessorial_id,
                    "description": item.description,
                    "quantity": item.quantity,
                    "unit_of_measure": item.unit_of_measure,
                    "unit_rate": item.unit_rate,
                    "billed_amount": item.expected_amount,
                    "expected_amount": item.expected_amount,
                    "variance_amount": 0.0,
                    "evidence_reference": item.evidence_reference,
                    "source_reference": item.source_reference
                })

            lines.append({
                "line_number": len(lines) + 1,
                "line_type": "ACCESSORIAL",
                "accessorial_id": None,
                "description": f"Unauthorized {unauth_code} Service (No Delivery POD Evidence)",
                "quantity": 1.0,
                "unit_of_measure": "FLAT",
                "unit_rate": fee,
                "billed_amount": fee,
                "expected_amount": 0.0,
                "variance_amount": fee,
                "evidence_reference": None, # Unverified!
                "source_reference": "UNCONTRACTED_FEE"
            })
            total_billed = round(baseline_calc.total_expected_amount + fee, 2)
            return AnomalyInjectionResult(
                issue_type=issue_type,
                is_anomaly=True,
                expected_decision="FAIL",
                raw_shipment_ref=shipment.shipment_id,
                shipment_id=shipment.shipment_id,
                reference_rejection_reason=None,
                injected_lines=lines,
                total_billed=total_billed,
                ground_truth_expected=baseline_calc.total_expected_amount,
                injected_variance=injected_variance,
                anomaly_id=anomaly_id,
                injection_method="UNAUTHORIZED_ACCESSORIAL_NO_EVIDENCE",
                affected_entity_ids=affected_ids,
                details={"unauthorized_code": unauth_code, "billed_fee": fee}
            )

        # -------------------------------------------------------------
        # Anomaly G: Duplicate Billing
        # -------------------------------------------------------------
        elif issue_type == "DUPLICATE_BILLING":
            for idx, item in enumerate(baseline_calc.charge_items):
                lines.append({
                    "line_number": idx + 1,
                    "line_type": item.charge_type,
                    "accessorial_id": item.accessorial_id,
                    "description": item.description,
                    "quantity": item.quantity,
                    "unit_of_measure": item.unit_of_measure,
                    "unit_rate": item.unit_rate,
                    "billed_amount": item.expected_amount,
                    "expected_amount": item.expected_amount,
                    "variance_amount": 0.0,
                    "evidence_reference": item.evidence_reference,
                    "source_reference": item.source_reference
                })
            total_billed = baseline_calc.total_expected_amount
            return AnomalyInjectionResult(
                issue_type=issue_type,
                is_anomaly=True,
                expected_decision="FAIL",
                raw_shipment_ref=shipment.shipment_id,
                shipment_id=shipment.shipment_id,
                reference_rejection_reason=None,
                injected_lines=lines,
                total_billed=total_billed,
                ground_truth_expected=0.0, # Duplicate invoice should have 0 expected payable
                injected_variance=total_billed,
                anomaly_id=anomaly_id,
                injection_method="DUPLICATE_INVOICE_SUBMISSION",
                affected_entity_ids=affected_ids,
                details={"duplicate_of_shipment": shipment.shipment_id}
            )

        # Fallback default
        else:
            return cls.apply_anomaly("NORMAL", counter, invoice_id, shipment, rate_card, baseline_calc, carrier, rng)
