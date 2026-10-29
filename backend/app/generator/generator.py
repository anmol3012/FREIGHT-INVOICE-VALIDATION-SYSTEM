"""
Production-Grade Deterministic Synthetic Data Generator for Freight Invoice Validation System.
Generates all 17 relational entities in strict dependency order:
  1. Carriers (Carrier)
  2. Lanes (Lane)
  3. Accessorial definitions (Accessorial)
  4. Rate cards (RateCard)
  5. Rate tiers (RateTier)
  6. Shipments (Shipment)
  7. Shipment legs (ShipmentLeg)
  8. Weight measurements (WeightMeasurement)
  9. Shipment-accessorial assignments (ShipmentAccessorial)
  10. Delivery evidence and events (DeliveryEvidence)
  11. Freight invoices (FreightInvoice)
  12. Invoice lines (InvoiceLine)
  13. Validation results (InvoiceValidationRun)
  14. Audit exceptions (AuditException)
  15. Credit notes (CreditNote)
  16. Audit and lifecycle events (AuditEvent, EntityStatusHistory)
  17. Ground-truth labels (GroundTruthLabel)
"""

import json
import random
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Tuple, Optional
from sqlalchemy.orm import Session

from backend.app.generator.config import PROFILES, GeneratorProfile, LOGISTICS_HUBS, CARRIER_SEEDS
from backend.app.generator.anomaly_injector import AnomalyInjector
from backend.app.engine.calculator import ContractualFreightCalculator
from backend.app.models.enums import (
    CarrierStatus, RateCardStatus, LaneStatus, ServiceLevel, ShipmentStatus,
    ShipmentLegStatus, MeasurementType, MeasurementSource, ChargeMethod,
    AccessorialStatus, InvoiceStatus, ValidationStatus, InvoiceLineType,
    ExceptionType, ExceptionSeverity, ExceptionStatus,
    CreditNoteApprovalStatus, CreditNoteReconciliationStatus
)
from backend.app.models.carrier import Carrier
from backend.app.models.lane import Lane
from backend.app.models.rate_card import RateCard, RateTier
from backend.app.models.accessorial import Accessorial, ShipmentAccessorial
from backend.app.models.shipment import Shipment, ShipmentLeg, WeightMeasurement, DeliveryEvidence
from backend.app.models.invoice import FreightInvoice, InvoiceLine, DuplicateInvoiceGroup, InvoiceValidationRun
from backend.app.models.audit_exception import AuditException
from backend.app.models.credit_note import CreditNote
from backend.app.models.audit import AuditEvent, EntityStatusHistory
from backend.app.models.ground_truth import GroundTruthLabel
from backend.app.models.id_generator import (
    generate_carrier_id, generate_rate_card_id, generate_lane_id, generate_rate_tier_id,
    generate_shipment_id, generate_shipment_leg_id, generate_weight_measurement_id,
    generate_accessorial_id, generate_shipment_accessorial_id, generate_delivery_evidence_id,
    generate_invoice_id, generate_invoice_line_id, generate_exception_id, generate_credit_note_id,
    generate_duplicate_group_id, generate_validation_run_id, generate_audit_event_id,
    generate_status_history_id, generate_ground_truth_label_id
)

BASE_EPOCH = datetime(2026, 1, 1, 8, 0, 0)
BASE_DATE = date(2026, 1, 1)

STANDARD_ACCESSORIALS = [
    ("LIFTGATE", "Hydraulic Liftgate Loading/Unloading Service", ChargeMethod.FLAT, 75.0, False, True),
    ("DETENTION", "Driver/Vehicle Detention at Terminal Facility", ChargeMethod.PER_HOUR, 80.0, False, True),
    ("RESIDENTIAL", "Residential Location Delivery Surcharge", ChargeMethod.FLAT, 65.0, False, True),
    ("INSIDE_DELIVERY", "Inside Delivery Beyond Dock Surcharge", ChargeMethod.FLAT, 55.0, False, True),
    ("HAZMAT", "Dangerous Goods & Hazardous Materials Protocol", ChargeMethod.FLAT, 120.0, True, True),
    ("APPOINTMENT", "Mandatory Guaranteed Delivery Time Window", ChargeMethod.FLAT, 35.0, False, True),
    ("RECONSIGNMENT", "In-Transit Destination Reconsignment Fee", ChargeMethod.FLAT, 110.0, False, True),
    ("STORAGE", "Overnight Depot Storage & Holding Surcharge", ChargeMethod.FLAT, 45.0, False, False),
]


# Guaranteed to exhibit all scenarios even in small test runs (>= 20 invoices)
SCENARIO_CYCLE = [
    "NORMAL",
    "NORMAL",
    "UNKNOWN_SHIPMENT_REF",
    "NORMAL",
    "EXPIRED_RATE_CARD",
    "NORMAL",
    "INCORRECT_WEIGHT_TIER",
    "NORMAL",
    "NORMAL",
    "DUPLICATE_FUEL_SURCHARGE",
    "NORMAL",
    "EXCESSIVE_CREDIT_NOTE",
    "NORMAL",
    "DIMENSIONAL_WEIGHT_DISCREPANCY",
    "NORMAL",
    "NORMAL",
    "UNAUTHORIZED_ACCESSORIAL",
    "NORMAL",
    "DUPLICATE_INVOICE",
    "NORMAL",
]


class DeterministicDataGenerator:
    """
    Configurable, 100% reproducible synthetic data generator.
    Implements all 17 entity generation steps in strict dependency order.
    """

    def __init__(self, profile_name: str = "starter", seed: int = 20261022):
        self.profile = PROFILES.get(profile_name, PROFILES["starter"])
        self.seed = seed
        self.rng = random.Random(seed)
        self.audit_event_seq = 1
        self.status_hist_seq = 1

    def generate_all(
        self,
        db: Session,
        num_carriers: Optional[int] = None,
        num_shipments: Optional[int] = None,
        num_invoices: Optional[int] = None
    ) -> Dict[str, int]:
        """
        Executes complete 17-step dependency generation pipeline.
        """
        self.rng.seed(self.seed)
        self.audit_event_seq = 1
        self.status_hist_seq = 1

        n_carriers = num_carriers if num_carriers is not None else self.profile.num_carriers
        n_lanes = self.profile.num_lanes
        n_accessorials = self.profile.num_accessorials
        n_shipments = num_shipments if num_shipments is not None else self.profile.num_shipments
        n_invoices = num_invoices if num_invoices is not None else self.profile.num_invoices

        counts: Dict[str, int] = {}

        # 1. Carriers
        carriers = self._generate_carriers(db, n_carriers)
        counts["carriers"] = len(carriers)

        # 2. Lanes
        lanes = self._generate_lanes(db, n_lanes)
        counts["lanes"] = len(lanes)

        # 3. Accessorial Catalog
        accessorials = self._generate_accessorials(db, n_accessorials)
        counts["accessorials"] = len(accessorials)

        # 4 & 5. Rate Cards & Rate Tiers
        rate_cards, rate_tiers = self._generate_rate_cards_and_tiers(db, carriers, lanes)
        counts["rate_cards"] = len(rate_cards)
        counts["rate_tiers"] = len(rate_tiers)

        # 6, 7, 8, 9, 10. Shipments, Legs, Weight Measurements, Accessorials, Delivery Evidence
        (shipments, legs, weights, shipment_accs, evidences) = self._generate_shipments_and_movements(
            db, carriers, lanes, accessorials, rate_cards, n_shipments
        )
        counts["shipments"] = len(shipments)
        counts["shipment_legs"] = len(legs)
        counts["weight_measurements"] = len(weights)
        counts["shipment_accessorials"] = len(shipment_accs)
        counts["delivery_evidence"] = len(evidences)

        # 11, 12, 13, 14, 15, 17. Invoices, Lines, Validation Runs, Exceptions, Credit Notes, Ground Truth
        (invoices, lines, val_runs, exceptions, credit_notes, ground_truths, dup_groups) = self._generate_invoices_and_financials(
            db, carriers, shipments, rate_cards, accessorials, evidences, shipment_accs, n_invoices
        )
        counts["duplicate_invoice_groups"] = len(dup_groups)
        counts["freight_invoices"] = len(invoices)
        counts["invoice_lines"] = len(lines)
        counts["invoice_validation_runs"] = len(val_runs)
        counts["audit_exceptions"] = len(exceptions)
        counts["credit_notes"] = len(credit_notes)
        counts["ground_truth_labels"] = len(ground_truths)

        # 16. Operational Audit Events and Lifecycle Transitions
        audit_events, status_histories = self._generate_audit_trail(db, carriers, shipments, invoices, exceptions, credit_notes)
        counts["audit_events"] = len(audit_events)
        counts["entity_status_history"] = len(status_histories)

        db.commit()
        return counts

    # -------------------------------------------------------------------------
    # 1. Carriers
    # -------------------------------------------------------------------------
    def _generate_carriers(self, db: Session, count: int) -> List[Carrier]:
        carriers = []
        for i in range(1, count + 1):
            seed_idx = (i - 1) % len(CARRIER_SEEDS)
            code, name = CARRIER_SEEDS[seed_idx]
            if i > len(CARRIER_SEEDS):
                code = f"{code[:3]}{i}"
                name = f"{name} Fleet {i}"

            cid = generate_carrier_id(i)
            c = Carrier(
                carrier_id=cid,
                carrier_name=name,
                carrier_code=code,
                status=CarrierStatus.ACTIVE,
                country_code="USA",
                created_at=BASE_EPOCH + timedelta(minutes=i * 5),
                updated_at=BASE_EPOCH + timedelta(minutes=i * 5)
            )
            db.add(c)
            carriers.append(c)
        db.flush()
        return carriers

    # -------------------------------------------------------------------------
    # 2. Lanes
    # -------------------------------------------------------------------------
    def _generate_lanes(self, db: Session, count: int) -> List[Lane]:
        lanes = []
        pairs_used = set()
        lane_counter = 1

        while len(lanes) < count:
            hub_a = self.rng.choice(LOGISTICS_HUBS)
            hub_b = self.rng.choice(LOGISTICS_HUBS)
            if hub_a[0] == hub_b[0]:
                continue
            pair = (hub_a[0], hub_b[0])
            if pair in pairs_used:
                continue
            pairs_used.add(pair)

            lid = generate_lane_id(lane_counter)
            lane_counter += 1
            dist = round(self.rng.uniform(220.0, 3200.0), 1)

            lane = Lane(
                lane_id=lid,
                origin_location_code=hub_a[0],
                destination_location_code=hub_b[0],
                origin_city=hub_a[1],
                destination_city=hub_b[1],
                origin_country=hub_a[2],
                destination_country=hub_b[2],
                distance_km=dist,
                status=LaneStatus.ACTIVE
            )
            db.add(lane)
            lanes.append(lane)
        db.flush()
        return lanes

    # -------------------------------------------------------------------------
    # 3. Accessorial Catalog
    # -------------------------------------------------------------------------
    def _generate_accessorials(self, db: Session, count: int) -> List[Accessorial]:
        accessorials = []
        catalog = STANDARD_ACCESSORIALS[:count]
        for i, (code, desc, method, rate, tax, proof) in enumerate(catalog, start=1):
            acc_id = generate_accessorial_id(i)
            acc = Accessorial(
                accessorial_id=acc_id,
                accessorial_code=code,
                description=desc,
                charge_method=method,
                rate_amount=rate,
                currency="USD",
                taxable=tax,
                requires_evidence=proof,
                status=AccessorialStatus.ACTIVE,
                effective_from=BASE_DATE,
                effective_to=None
            )
            db.add(acc)
            accessorials.append(acc)
        db.flush()
        return accessorials

    # -------------------------------------------------------------------------
    # 4 & 5. Rate Cards and Rate Tiers
    # -------------------------------------------------------------------------
    def _generate_rate_cards_and_tiers(
        self, db: Session, carriers: List[Carrier], lanes: List[Lane]
    ) -> Tuple[List[RateCard], List[RateTier]]:
        rate_cards = []
        rate_tiers = []

        card_counter = 1
        for carrier in carriers:
            # Assign 2-5 lanes per carrier
            assigned_lanes = self.rng.sample(lanes, min(len(lanes), self.rng.randint(2, 5)))
            for lane in assigned_lanes:
                rc_id = generate_rate_card_id(carrier.carrier_id, 2026, card_counter)
                card_counter += 1

                base_rt = round(self.rng.uniform(0.35, 0.75), 4)
                min_chg = round(self.rng.uniform(65.0, 110.0), 2)

                rc = RateCard(
                    rate_card_id=rc_id,
                    carrier_id=carrier.carrier_id,
                    lane_id=lane.lane_id,
                    service_level=ServiceLevel.STANDARD,
                    currency="USD",
                    effective_from=BASE_DATE,
                    effective_to=BASE_DATE + timedelta(days=364),
                    base_rate=base_rt,
                    minimum_charge=min_chg,
                    dimensional_weight_divisor=5000.0,
                    status=RateCardStatus.ACTIVE,
                    created_at=BASE_EPOCH + timedelta(hours=card_counter)
                )
                db.add(rc)
                rate_cards.append(rc)

                # Weight tiers
                tier_configs = [
                    (1, 0.0, 250.0, round(base_rt * 1.30, 4), 0.0),
                    (2, 250.0, 1000.0, round(base_rt * 1.10, 4), 0.0),
                    (3, 1000.0, 5000.0, round(base_rt * 0.95, 4), 0.0),
                    (4, 5000.0, None, round(base_rt * 0.85, 4), 25.0),
                ]
                for seq, min_w, max_w, rate_kg, surch in tier_configs:
                    tier_id = generate_rate_tier_id(rc_id, seq)
                    tier = RateTier(
                        rate_tier_id=tier_id,
                        rate_card_id=rc_id,
                        tier_sequence=seq,
                        min_weight_kg=min_w,
                        max_weight_kg=max_w,
                        rate_per_kg=rate_kg,
                        flat_surcharge=surch,
                        created_at=BASE_EPOCH + timedelta(hours=card_counter)
                    )
                    db.add(tier)
                    rate_tiers.append(tier)

        db.flush()
        return rate_cards, rate_tiers

    # -------------------------------------------------------------------------
    # 6, 7, 8, 9, 10. Shipments, Legs, Weights, Accessorials, Delivery Evidence
    # -------------------------------------------------------------------------
    def _generate_shipments_and_movements(
        self,
        db: Session,
        carriers: List[Carrier],
        lanes: List[Lane],
        accessorials: List[Accessorial],
        rate_cards: List[RateCard],
        count: int
    ) -> Tuple[List[Shipment], List[ShipmentLeg], List[WeightMeasurement], List[ShipmentAccessorial], List[DeliveryEvidence]]:
        shipments = []
        legs = []
        weights = []
        shipment_accs = []
        evidences = []

        acc_by_code = {a.accessorial_code: a for a in accessorials}
        lane_map = {l.lane_id: l for l in lanes}
        carrier_rc_map: Dict[str, List[RateCard]] = {}
        for rc in rate_cards:
            carrier_rc_map.setdefault(rc.carrier_id, []).append(rc)

        for i in range(1, count + 1):
            carrier = carriers[(i - 1) % len(carriers)]
            c_cards = carrier_rc_map.get(carrier.carrier_id) or rate_cards
            assigned_card = c_cards[(i - 1) % len(c_cards)]
            lane = lane_map.get(assigned_card.lane_id) or lanes[(i - 1) % len(lanes)]
            ship_id = generate_shipment_id(i)

            ship_d = BASE_DATE + timedelta(days=self.rng.randint(5, 280))
            transit = max(1, int(lane.distance_km / 750.0) + self.rng.randint(0, 1))
            due_d = ship_d + timedelta(days=transit)
            deliv_dt = datetime.combine(due_d, datetime.min.time()) + timedelta(hours=self.rng.randint(9, 17), minutes=self.rng.randint(0, 59))

            l_cm = round(self.rng.uniform(80.0, 240.0), 1)
            w_cm = round(self.rng.uniform(60.0, 140.0), 1)
            h_cm = round(self.rng.uniform(60.0, 200.0), 1)
            act_kg = round(self.rng.uniform(45.0, 6500.0), 1)
            dec_kg = act_kg
            chg_kg = ContractualFreightCalculator.calculate_chargeable_weight(
                act_kg, l_cm, w_cm, h_cm, divisor=5000.0, rounding_policy=self.profile.weight_rounding
            )

            shipment = Shipment(
                shipment_id=ship_id,
                carrier_id=carrier.carrier_id,
                lane_id=lane.lane_id,
                service_level=ServiceLevel.STANDARD,
                ship_date=ship_d,
                delivery_due_date=due_d,
                delivered_at=deliv_dt,
                actual_length_cm=l_cm,
                actual_width_cm=w_cm,
                actual_height_cm=h_cm,
                actual_weight_kg=act_kg,
                declared_weight_kg=dec_kg,
                chargeable_weight_kg=chg_kg,
                currency="USD",
                shipment_status=ShipmentStatus.DELIVERED,
                created_at=datetime.combine(ship_d, datetime.min.time()) - timedelta(days=1)
            )
            db.add(shipment)
            shipments.append(shipment)

            # Leg
            leg_id = generate_shipment_leg_id(ship_id, 1)
            leg = ShipmentLeg(
                shipment_leg_id=leg_id,
                shipment_id=ship_id,
                leg_sequence=1,
                origin_location_code=lane.origin_location_code,
                destination_location_code=lane.destination_location_code,
                departure_at=datetime.combine(ship_d, datetime.min.time()) + timedelta(hours=8),
                arrival_at=deliv_dt,
                leg_status=ShipmentLegStatus.ARRIVED
            )
            db.add(leg)
            legs.append(leg)

            # Weight Measurement
            wm_id = generate_weight_measurement_id(ship_id, 1)
            wm = WeightMeasurement(
                weight_measurement_id=wm_id,
                shipment_id=ship_id,
                measurement_type=MeasurementType.ORIGIN_SCALE,
                length_cm=l_cm,
                width_cm=w_cm,
                height_cm=h_cm,
                weight_kg=act_kg,
                measured_at=datetime.combine(ship_d, datetime.min.time()) + timedelta(hours=7, minutes=30),
                source=MeasurementSource.CARRIER,
                is_accepted=True
            )
            db.add(wm)
            weights.append(wm)

            # Delivery Evidence
            dock_type = self.rng.choices(["STANDARD_DOCK", "GROUND_LEVEL", "RESIDENTIAL"], weights=[0.70, 0.22, 0.08])[0]
            liftgate_used = (dock_type in ["GROUND_LEVEL", "RESIDENTIAL"])
            detention_mins = self.rng.choice([0, 0, 0, 15, 30, 45, 120, 150, 180])

            dev_id = generate_delivery_evidence_id(ship_id)
            dev = DeliveryEvidence(
                delivery_evidence_id=dev_id,
                shipment_id=ship_id,
                delivered_at=deliv_dt,
                recipient_name=f"Dock Agent {self.rng.randint(101, 899)}",
                signed_pod_ref=f"POD-SIG-{ship_id}",
                facility_dock_type=dock_type,
                liftgate_actually_used=liftgate_used,
                detention_minutes_recorded=detention_mins,
                created_at=deliv_dt + timedelta(minutes=15)
            )
            db.add(dev)
            evidences.append(dev)

            # Accessorials assignments
            acc_seq = 1
            if liftgate_used and "LIFTGATE" in acc_by_code:
                sa_id = generate_shipment_accessorial_id(ship_id, acc_seq)
                acc_seq += 1
                sa = ShipmentAccessorial(
                    shipment_accessorial_id=sa_id,
                    shipment_id=ship_id,
                    accessorial_id=acc_by_code["LIFTGATE"].accessorial_id,
                    quantity=1.0,
                    authorized=True,
                    evidence_reference=f"POD-LIFTGATE-{ship_id}",
                    created_at=deliv_dt
                )
                db.add(sa)
                shipment_accs.append(sa)

            if detention_mins > 120 and "DETENTION" in acc_by_code:
                sa_id = generate_shipment_accessorial_id(ship_id, acc_seq)
                acc_seq += 1
                det_hours = round((detention_mins - 120) / 60.0, 2)
                sa = ShipmentAccessorial(
                    shipment_accessorial_id=sa_id,
                    shipment_id=ship_id,
                    accessorial_id=acc_by_code["DETENTION"].accessorial_id,
                    quantity=det_hours,
                    authorized=True,
                    evidence_reference=f"ELD-GPS-LOG-{ship_id}",
                    created_at=deliv_dt
                )
                db.add(sa)
                shipment_accs.append(sa)

            if i % 1000 == 0:
                db.flush()
            if i % 5000 == 0:
                print(f"    ... movements: {i:,}/{count:,} shipments", flush=True)

        db.flush()
        return shipments, legs, weights, shipment_accs, evidences

    # -------------------------------------------------------------------------
    # 11, 12, 13, 14, 15, 17. Invoices, Financials, Validation, Ground Truth
    # -------------------------------------------------------------------------
    def _generate_invoices_and_financials(
        self,
        db: Session,
        carriers: List[Carrier],
        shipments: List[Shipment],
        rate_cards: List[RateCard],
        accessorials: List[Accessorial],
        evidences: List[DeliveryEvidence],
        shipment_accs: List[ShipmentAccessorial],
        count: int
    ) -> Tuple[List[FreightInvoice], List[InvoiceLine], List[InvoiceValidationRun], List[AuditException], List[CreditNote], List[GroundTruthLabel], List[DuplicateInvoiceGroup]]:
        invoices = []
        lines = []
        validation_runs = []
        exceptions = []
        credit_notes = []
        ground_truths = []
        dup_groups = []

        # Index lookups
        carrier_map = {c.carrier_id: c for c in carriers}
        evid_map = {e.shipment_id: e for e in evidences}
        acc_map = {}
        for sa in shipment_accs:
            acc_map.setdefault(sa.shipment_id, []).append(sa)
        rc_map = {}
        for rc in rate_cards:
            rc_map.setdefault((rc.carrier_id, rc.lane_id), []).append(rc)

        dup_group_counter = 1
        exception_counter = 1
        credit_note_counter = 1
        gt_counter = 1

        for i in range(1, count + 1):
            issue_type = SCENARIO_CYCLE[(i - 1) % len(SCENARIO_CYCLE)]
            shipment = shipments[(i - 1) % len(shipments)]
            carrier = carrier_map.get(shipment.carrier_id) or carriers[(i - 1) % len(carriers)]

            carrier_rcs = rc_map.get((carrier.carrier_id, shipment.lane_id), [])
            rate_card = carrier_rcs[0] if carrier_rcs else None

            dev = evid_map.get(shipment.shipment_id)
            sa_list = acc_map.get(shipment.shipment_id, [])

            # Compute valid baseline calculation
            baseline_calc = ContractualFreightCalculator.rate_shipment(
                shipment=shipment,
                rate_card=rate_card,
                delivery_evidence=dev,
                shipment_accessorials=sa_list,
                weight_rounding=self.profile.weight_rounding
            )

            inv_id = generate_invoice_id(i)
            inv_date = shipment.delivery_due_date + timedelta(days=self.rng.randint(2, 7))
            due_date = inv_date + timedelta(days=30)
            inv_num = f"INV-{carrier.carrier_code}-{20260000 + i}"

            # Apply anomaly injector
            anom_result = AnomalyInjector.apply_anomaly(
                issue_type=issue_type,
                counter=i,
                invoice_id=inv_id,
                shipment=shipment,
                rate_card=rate_card,
                baseline_calc=baseline_calc,
                carrier=carrier,
                rng=self.rng
            )

            # Handle duplicate invoice group if duplicate scenario
            dup_grp_id = None
            if issue_type == "DUPLICATE_INVOICE":
                grp_id = generate_duplicate_group_id(dup_group_counter)
                dup_group_counter += 1
                fp_hash = f"HASH-DUP-{inv_id}"
                dup_grp = DuplicateInvoiceGroup(
                    group_id=grp_id,
                    carrier_id=carrier.carrier_id,
                    fingerprint_hash=fp_hash,
                    canonical_invoice_id=inv_id,
                    invoice_count=2,
                    created_at=datetime.combine(inv_date, datetime.min.time())
                )
                db.add(dup_grp)
                dup_groups.append(dup_grp)
                dup_grp_id = grp_id

            # Determine invoice and validation statuses
            if anom_result.expected_decision == "PASS":
                inv_status = InvoiceStatus.SUBMITTED
                val_status = ValidationStatus.PASSED
            else:
                inv_status = InvoiceStatus.EXCEPTION_DISPUTED
                val_status = ValidationStatus.FAILED

            finv = FreightInvoice(
                invoice_id=inv_id,
                carrier_id=carrier.carrier_id,
                shipment_id=anom_result.shipment_id, # NULL if untrusted ref
                raw_shipment_reference=anom_result.raw_shipment_ref,
                reference_rejection_reason=anom_result.reference_rejection_reason,
                invoice_number=inv_num,
                invoice_date=inv_date,
                service_period_start=shipment.ship_date,
                service_period_end=shipment.delivery_due_date,
                due_date=due_date,
                currency="USD",
                billed_total=anom_result.total_billed,
                expected_total=anom_result.ground_truth_expected,
                variance_amount=anom_result.injected_variance,
                invoice_status=inv_status,
                validation_status=val_status,
                duplicate_group_id=dup_grp_id,
                fingerprint_hash=f"FP-{carrier.carrier_id}-{anom_result.raw_shipment_ref}-{anom_result.total_billed}",
                created_at=datetime.combine(inv_date, datetime.min.time())
            )
            db.add(finv)
            invoices.append(finv)

            # Invoice Lines
            for line_data in anom_result.injected_lines:
                fline_id = generate_invoice_line_id(inv_id, line_data["line_number"])
                fline = InvoiceLine(
                    invoice_line_id=fline_id,
                    invoice_id=inv_id,
                    line_number=line_data["line_number"],
                    line_type=InvoiceLineType[line_data["line_type"]] if isinstance(line_data["line_type"], str) else line_data["line_type"],
                    accessorial_id=line_data.get("accessorial_id"),
                    description=line_data["description"],
                    quantity=line_data["quantity"],
                    unit_of_measure=line_data["unit_of_measure"],
                    unit_rate=line_data["unit_rate"],
                    billed_amount=line_data["billed_amount"],
                    expected_amount=line_data["expected_amount"],
                    variance_amount=line_data["variance_amount"],
                    evidence_reference=line_data.get("evidence_reference"),
                    source_reference=line_data.get("source_reference"),
                    created_at=datetime.combine(inv_date, datetime.min.time())
                )
                db.add(fline)
                lines.append(fline)

            # 13. Validation Run record
            vrun_id = generate_validation_run_id(i)
            vrun = InvoiceValidationRun(
                validation_run_id=vrun_id,
                invoice_id=inv_id,
                run_at=datetime.combine(inv_date, datetime.min.time()) + timedelta(hours=2),
                actor="AUTOMATED_AUDITOR_V1",
                rules_applied_count=5,
                exceptions_detected_count=1 if anom_result.is_anomaly else 0,
                summary_verdict=anom_result.expected_decision,
                details_json=json.dumps({
                    "issue_type": issue_type,
                    "expected_decision": anom_result.expected_decision,
                    "billed_total": anom_result.total_billed,
                    "expected_total": anom_result.ground_truth_expected,
                    "variance": anom_result.injected_variance
                })
            )
            db.add(vrun)
            validation_runs.append(vrun)

            # 14. Audit Exception (if anomaly/discrepancy detected)
            ex_id = None
            if anom_result.is_anomaly:
                ex_id = generate_exception_id(exception_counter)
                exception_counter += 1

                ex_type = ExceptionType.CALCULATION_ERROR
                if issue_type == "UNKNOWN_SHIPMENT_REF":
                    ex_type = ExceptionType.UNMATCHED_SHIPMENT
                elif issue_type == "EXPIRED_RATE_CARD":
                    ex_type = ExceptionType.BASE_RATE_MISMATCH
                elif issue_type == "INCORRECT_WEIGHT_TIER":
                    ex_type = ExceptionType.WEIGHT_DISCREPANCY
                elif issue_type == "DUPLICATE_FUEL_SURCHARGE":
                    ex_type = ExceptionType.DUPLICATE_BILLING
                elif issue_type == "DIMENSIONAL_WEIGHT_DISCREPANCY":
                    ex_type = ExceptionType.WEIGHT_DISCREPANCY
                elif issue_type == "UNAUTHORIZED_ACCESSORIAL":
                    ex_type = ExceptionType.UNAUTHORIZED_ACCESSORIAL
                elif issue_type == "DUPLICATE_INVOICE":
                    ex_type = ExceptionType.DUPLICATE_BILLING

                ex = AuditException(
                    exception_id=ex_id,
                    invoice_id=inv_id,
                    invoice_line_id=lines[-1].invoice_line_id if lines else None,
                    shipment_id=anom_result.shipment_id,
                    exception_type=ex_type,
                    severity=ExceptionSeverity.CRITICAL if anom_result.injected_variance > 100.0 else ExceptionSeverity.MEDIUM,
                    expected_amount=anom_result.ground_truth_expected,
                    billed_amount=anom_result.total_billed,
                    disputed_amount=anom_result.injected_variance,
                    currency="USD",
                    explanation=f"Audit discrepancy detected: {issue_type}. Billed ${anom_result.total_billed:.2f} vs contracted ${anom_result.ground_truth_expected:.2f}.",
                    evidence_json=json.dumps(anom_result.details),
                    exception_status=ExceptionStatus.OPEN,
                    detected_at=datetime.combine(inv_date, datetime.min.time()) + timedelta(hours=2)
                )
                db.add(ex)
                exceptions.append(ex)

            # 15. Credit Notes (Scenario E: Excessive Credit Note or Legitimate Settlement)
            if issue_type == "EXCESSIVE_CREDIT_NOTE" or (anom_result.is_anomaly and i % 7 == 0 and ex_id):
                cn_id = generate_credit_note_id(credit_note_counter)
                credit_note_counter += 1

                if issue_type == "EXCESSIVE_CREDIT_NOTE":
                    # Scenario E: Credit note exceeds approved disputed amount!
                    # Disputed variance is $100, credit note issued is $175 -> REJECTED
                    credit_val = round(anom_result.injected_variance + 75.0, 2)
                    cn_approval = CreditNoteApprovalStatus.REJECTED
                    cn_recon = CreditNoteReconciliationStatus.REJECTED
                else:
                    # Legitimate settlement matching dispute
                    credit_val = anom_result.injected_variance
                    cn_approval = CreditNoteApprovalStatus.APPROVED
                    cn_recon = CreditNoteReconciliationStatus.FULLY_APPLIED

                cn = CreditNote(
                    credit_note_id=cn_id,
                    exception_id=ex_id,
                    invoice_id=inv_id,
                    carrier_id=carrier.carrier_id,
                    credit_note_number=f"CN-{carrier.carrier_code}-{20260000 + credit_note_counter}",
                    issue_date=inv_date + timedelta(days=14),
                    currency="USD",
                    credit_amount=credit_val,
                    approval_status=cn_approval,
                    reconciliation_status=cn_recon,
                    created_at=datetime.combine(inv_date + timedelta(days=14), datetime.min.time())
                )
                db.add(cn)
                credit_notes.append(cn)

            # 17. Ground Truth Label (Evaluation dataset)
            gtl_id = generate_ground_truth_label_id(gt_counter)
            gt_counter += 1

            gt = GroundTruthLabel(
                label_id=gtl_id,
                anomaly_id=anom_result.anomaly_id,
                invoice_id=inv_id,
                invoice_number=inv_num,
                raw_shipment_reference=anom_result.raw_shipment_ref,
                carrier_id=carrier.carrier_id,
                carrier_code=carrier.carrier_code,
                issue_type=issue_type,
                is_anomaly=anom_result.is_anomaly,
                expected_decision=anom_result.expected_decision,
                affected_entity_ids_json=json.dumps(anom_result.affected_entity_ids),
                injection_method=anom_result.injection_method,
                ground_truth_billed=anom_result.total_billed,
                ground_truth_expected=anom_result.ground_truth_expected,
                injected_variance=anom_result.injected_variance,
                details_json=json.dumps(anom_result.details),
                created_at=datetime.combine(inv_date, datetime.min.time())
            )
            db.add(gt)
            ground_truths.append(gt)

            if i % 1000 == 0:
                db.flush()
            if i % 5000 == 0:
                print(f"    ... financials: {i:,}/{count:,} invoices", flush=True)

        db.flush()
        return invoices, lines, validation_runs, exceptions, credit_notes, ground_truths, dup_groups

    # -------------------------------------------------------------------------
    # 16. Audit Events and Entity Status History
    # -------------------------------------------------------------------------
    def _generate_audit_trail(
        self,
        db: Session,
        carriers: List[Carrier],
        shipments: List[Shipment],
        invoices: List[FreightInvoice],
        exceptions: List[AuditException],
        credit_notes: List[CreditNote]
    ) -> Tuple[List[AuditEvent], List[EntityStatusHistory]]:
        audit_events = []
        status_histories = []

        # System start event
        ev_id = generate_audit_event_id(self.audit_event_seq)
        self.audit_event_seq += 1
        ev = AuditEvent(
            event_id=ev_id,
            entity_type="SYSTEM",
            entity_id="GENERATOR",
            event_type="SYNTHESIS_STARTED",
            actor="DATA_GENERATOR",
            payload_json=json.dumps({"profile": self.profile.name, "seed": self.seed}),
            notes="Starting synthetic freight dataset generation",
            timestamp=BASE_EPOCH
        )
        db.add(ev)
        audit_events.append(ev)

        # Record sample shipment and invoice lifecycle history
        for inv in invoices[:min(len(invoices), 50)]:
            hist_id = generate_status_history_id(self.status_hist_seq)
            self.status_hist_seq += 1
            sh = EntityStatusHistory(
                history_id=hist_id,
                entity_name="FreightInvoice",
                entity_id=inv.invoice_id,
                from_status="NONE",
                to_status=inv.invoice_status.value if hasattr(inv.invoice_status, "value") else str(inv.invoice_status),
                transition_reason="Initial invoice submission and audit ingestion",
                changed_by="INGESTION_PIPELINE",
                changed_at=datetime.combine(inv.invoice_date, datetime.min.time())
            )
            db.add(sh)
            status_histories.append(sh)

        for ex in exceptions[:min(len(exceptions), 25)]:
            hist_id = generate_status_history_id(self.status_hist_seq)
            self.status_hist_seq += 1
            sh = EntityStatusHistory(
                history_id=hist_id,
                entity_name="AuditException",
                entity_id=ex.exception_id,
                from_status="NONE",
                to_status=ex.exception_status.value if hasattr(ex.exception_status, "value") else str(ex.exception_status),
                transition_reason="Variance identified by audit engine",
                changed_by="AUDIT_ENGINE",
                changed_at=ex.detected_at
            )
            db.add(sh)
            status_histories.append(sh)

        # System completion event
        ev_id = generate_audit_event_id(self.audit_event_seq)
        self.audit_event_seq += 1
        ev = AuditEvent(
            event_id=ev_id,
            entity_type="SYSTEM",
            entity_id="GENERATOR",
            event_type="SYNTHESIS_COMPLETED",
            actor="DATA_GENERATOR",
            payload_json=json.dumps({
                "carriers": len(carriers),
                "shipments": len(shipments),
                "invoices": len(invoices),
                "exceptions": len(exceptions),
                "credit_notes": len(credit_notes)
            }),
            notes="Dataset synthesis finished successfully",
            timestamp=BASE_EPOCH + timedelta(days=365)
        )
        db.add(ev)
        audit_events.append(ev)

        db.flush()
        return audit_events, status_histories


# Backward compatibility alias
SyntheticDataGenerator = DeterministicDataGenerator
