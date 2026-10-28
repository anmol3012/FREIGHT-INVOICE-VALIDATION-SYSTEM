import random
import json
import hashlib
from datetime import datetime, date, timedelta
from typing import List, Dict, Tuple
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.models.carrier import Carrier
from backend.app.models.rate_card import RateCard, RateLane, AccessorialRule
from backend.app.models.shipment import Shipment, WeightMeasurement, AccessorialEvent, DeliveryRecord
from backend.app.models.invoice import InvoiceHeader, InvoiceLine
from backend.app.models.credit_note import CreditNote
from backend.app.models.ground_truth import GroundTruthLabel
from backend.app.models.audit import AuditEvent
from backend.app.engine.calculator import FreightCalculator
from backend.app.engine.validator import InvoiceValidator

CITIES = [
    ("Atlanta", "GA", "30301"),
    ("Chicago", "IL", "60601"),
    ("Dallas", "TX", "75201"),
    ("Los Angeles", "CA", "90001"),
    ("New York", "NY", "10001"),
    ("Seattle", "WA", "98101"),
    ("Miami", "FL", "33101"),
    ("Denver", "CO", "80201"),
    ("Philadelphia", "PA", "19101"),
    ("Houston", "TX", "77001"),
    ("Phoenix", "AZ", "85001"),
    ("Charlotte", "NC", "28201"),
    ("Detroit", "MI", "48201"),
    ("Memphis", "TN", "38101"),
    ("Indianapolis", "IN", "46201"),
]

SCACS = [
    "ODFL", "FXFE", "KNIG", "SAIA", "ABFS", "XPOF", "ESTES", "RLCA", "YELL", "AACT",
    "SEFL", "CTII", "DAFG", "PITT", "CWCE", "UPGF", "MTRC", "AVER", "CVLG", "WERN",
    "JBHT", "SCHN", "USXI", "SWFT", "HEAR", "MART", "CRST", "PTSI", "COSS", "DAYR"
]

class SyntheticDataGenerator:
    """
    Deterministic Synthetic Logistics & Billing Data Generator.
    Supports starter configurations and full 100-carrier / 20k-shipment / 15k-invoice scale.
    """

    def __init__(self, seed: int = settings.DEFAULT_RANDOM_SEED):
        self.seed = seed
        self.rng = random.Random(seed)

    def generate_all(
        self,
        db: Session,
        num_carriers: int = settings.STARTER_CARRIERS,
        num_shipments: int = settings.STARTER_SHIPMENTS,
        num_invoices: int = settings.STARTER_INVOICES
    ) -> Dict[str, int]:
        """
        Generate complete master data, shipments, invoices, ground truth labels, and credit notes.
        """
        # Reset RNG seed for reproducibility
        self.rng.seed(self.seed)

        # 1. Master Data: Carriers
        carriers = self._generate_carriers(db, num_carriers)
        
        # 2. Master Data: Rate Cards, Lanes, Accessorial Rules
        rate_cards, accessorial_rules = self._generate_contracts(db, carriers)

        # 3. Operational Data: Shipments, Weights, Deliveries, Events
        shipments = self._generate_shipments(db, carriers, num_shipments)

        # 4. Financial Data: Invoices, Invoice Lines, Ground Truth Labels
        invoices, ground_truths = self._generate_invoices_and_ground_truth(
            db, carriers, shipments, rate_cards, accessorial_rules, num_invoices
        )

        # 5. Credit Notes (Scenario 5)
        credit_notes = self._generate_credit_notes(db, carriers, invoices)

        # Log completion audit event
        db.add(AuditEvent(
            entity_type="SYSTEM",
            entity_id="GENERATOR",
            event_type="SYNTHESIS_COMPLETED",
            actor="DATA_GENERATOR",
            payload_json=json.dumps({
                "carriers": len(carriers),
                "shipments": len(shipments),
                "invoices": len(invoices),
                "ground_truth_labels": len(ground_truths),
                "credit_notes": len(credit_notes),
                "seed": self.seed
            }),
            notes=f"Synthetic dataset generated with seed {self.seed}"
        ))
        db.commit()

        return {
            "carriers": len(carriers),
            "shipments": len(shipments),
            "invoices": len(invoices),
            "ground_truth_labels": len(ground_truths),
            "credit_notes": len(credit_notes)
        }

    def _generate_carriers(self, db: Session, count: int) -> List[Carrier]:
        carriers = []
        for i in range(count):
            scac = SCACS[i % len(SCACS)] if i < len(SCACS) else f"CAR{i+1:03d}"
            carrier = Carrier(
                carrier_code=scac,
                name=f"{scac} Freight Logistics Corp #{i+1}",
                tax_id=f"12-{self.rng.randint(1000000, 9999999)}",
                payment_terms_days=self.rng.choice([15, 30, 45]),
                status="ACTIVE",
                contact_email=f"billing@{scac.lower()}freight.com"
            )
            db.add(carrier)
            carriers.append(carrier)
        db.flush()
        return carriers

    def _generate_contracts(self, db: Session, carriers: List[Carrier]) -> Tuple[List[RateCard], List[AccessorialRule]]:
        rate_cards = []
        accessorial_rules = []

        base_date = date(2026, 1, 1)

        for carrier in carriers:
            # Create active rate card
            rc = RateCard(
                rate_card_code=f"RC-{carrier.carrier_code}-2026",
                carrier_id=carrier.id,
                effective_date=base_date,
                expiration_date=base_date + timedelta(days=365),
                currency="USD",
                base_rate_model=self.rng.choice(["PER_CWT", "PER_CWT", "PER_MILE"]), # 67% CWT, 33% PER_MILE
                minimum_charge_floor=self.rng.choice([65.0, 75.0, 85.0]),
                fuel_base_price=3.00,
                fuel_surcharge_pct_per_interval=0.005,
                status="ACTIVE"
            )
            db.add(rc)
            db.flush()
            rate_cards.append(rc)

            # Lanes
            lane_cwt = round(self.rng.uniform(9.50, 16.50), 2)
            lane_mile = round(self.rng.uniform(1.85, 2.75), 2)
            lane = RateLane(
                rate_card_id=rc.id,
                origin_zip_prefix="ALL",
                dest_zip_prefix="ALL",
                origin_region="US-NATIONAL",
                dest_region="US-NATIONAL",
                base_rate_cwt=lane_cwt,
                base_rate_per_mile=lane_mile,
                flat_rate=round(self.rng.uniform(350.0, 750.0), 2),
                minimum_charge=rc.minimum_charge_floor,
                transit_days=self.rng.randint(1, 4)
            )
            db.add(lane)

            # Accessorial Rules
            rules_config = [
                ("LIFTGATE", "Liftgate Delivery Service", "FLAT", round(self.rng.uniform(65.0, 95.0), 2), 0, True),
                ("DETENTION", "Driver Detention at Facility", "PER_HOUR", round(self.rng.uniform(60.0, 90.0), 2), 120, True),
                ("RESIDENTIAL", "Residential Delivery Surcharge", "FLAT", round(self.rng.uniform(45.0, 75.0), 2), 0, True),
                ("INSIDE_DELIVERY", "Inside Delivery", "FLAT", round(self.rng.uniform(55.0, 85.0), 2), 0, True),
                ("HAZMAT", "Hazardous Material Handling", "FLAT", round(self.rng.uniform(110.0, 150.0), 2), 0, True),
                ("APPOINTMENT", "Guaranteed Delivery Appointment", "FLAT", 35.0, 0, True),
            ]
            for code, name, rtype, rate, free_time, req_proof in rules_config:
                ar = AccessorialRule(
                    carrier_id=carrier.id,
                    code=code,
                    name=name,
                    rate_type=rtype,
                    unit_rate=rate,
                    free_time_minutes=free_time,
                    proof_required=req_proof
                )
                db.add(ar)
                accessorial_rules.append(ar)

        db.flush()
        return rate_cards, accessorial_rules

    def _generate_shipments(self, db: Session, carriers: List[Carrier], count: int) -> List[Shipment]:
        shipments = []
        base_date = date(2026, 2, 1)

        for i in range(count):
            carrier = carriers[i % len(carriers)]
            orig_city, orig_state, orig_zip = self.rng.choice(CITIES)
            dest_city, dest_state, dest_zip = self.rng.choice(CITIES)
            while dest_city == orig_city:
                dest_city, dest_state, dest_zip = self.rng.choice(CITIES)

            p_date = base_date + timedelta(days=self.rng.randint(0, 180))
            d_date = p_date + timedelta(days=self.rng.randint(1, 4))
            dist = round(self.rng.uniform(80.0, 1400.0), 1)

            dock_type = self.rng.choices(["STANDARD_DOCK", "GROUND_LEVEL", "RESIDENTIAL"], weights=[0.75, 0.20, 0.05])[0]

            bol = f"BOL-{carrier.carrier_code}-{20260000 + i + 1}"
            shipment = Shipment(
                bol_number=bol,
                carrier_id=carrier.id,
                origin_zip=orig_zip,
                origin_city=orig_city,
                origin_state=orig_state,
                destination_zip=dest_zip,
                destination_city=dest_city,
                destination_state=dest_state,
                pickup_date=p_date,
                delivery_date=d_date,
                distance_miles=dist,
                current_fuel_index=round(self.rng.uniform(3.60, 4.25), 2),
                dock_type=dock_type,
                status="DELIVERED"
            )
            db.add(shipment)
            db.flush()

            # Certified scale weight
            gross_wt = round(self.rng.uniform(350.0, 18500.0), 1)
            l = round(self.rng.uniform(36.0, 96.0), 1)
            w = round(self.rng.uniform(36.0, 48.0), 1)
            h = round(self.rng.uniform(36.0, 84.0), 1)
            billable_wt = FreightCalculator.calculate_billable_weight(gross_wt, l, w, h, 139.0)

            wm = WeightMeasurement(
                shipment_id=shipment.id,
                measurement_type="ORIGIN_SCALE",
                gross_weight_lbs=gross_wt,
                length_in=l,
                width_in=w,
                height_in=h,
                dim_factor=139.0,
                billable_weight_lbs=billable_wt,
                certified=True
            )
            db.add(wm)

            # Delivery Record
            liftgate_used = (dock_type in ["GROUND_LEVEL", "RESIDENTIAL"])
            # Dwell time (mostly under 120 min free time, occasionally detention)
            dwell = self.rng.choice([45, 60, 75, 90, 110, 115, 145, 180, 240])

            dr = DeliveryRecord(
                shipment_id=shipment.id,
                delivered_at=datetime.combine(d_date, datetime.min.time()) + timedelta(hours=self.rng.randint(9, 17)),
                recipient_name=f"Dock Mgr {self.rng.randint(101, 999)}",
                signed_pod_ref=f"POD-SIG-{bol}",
                facility_dock_type=dock_type,
                liftgate_actually_used=liftgate_used,
                detention_minutes_recorded=dwell
            )
            db.add(dr)

            # Accessorial events if any
            if dwell > 120:
                db.add(AccessorialEvent(
                    shipment_id=shipment.id,
                    code="DETENTION",
                    quantity_or_duration=round((dwell - 120) / 60.0, 2),
                    proof_document_ref=f"GPS-ELD-LOG-{bol}",
                    authorized=True,
                    notes=f"Recorded dwell time {dwell} min"
                ))

            if liftgate_used:
                db.add(AccessorialEvent(
                    shipment_id=shipment.id,
                    code="LIFTGATE",
                    quantity_or_duration=1.0,
                    proof_document_ref=f"POD-LIFTGATE-SIGN-{bol}",
                    authorized=True,
                    notes="Ground delivery required liftgate"
                ))

            shipments.append(shipment)

        db.flush()
        return shipments

    def _generate_invoices_and_ground_truth(
        self,
        db: Session,
        carriers: List[Carrier],
        shipments: List[Shipment],
        rate_cards: List[RateCard],
        accessorial_rules: List[AccessorialRule],
        count: int
    ) -> Tuple[List[InvoiceHeader], List[GroundTruthLabel]]:
        invoices = []
        ground_truths = []

        carrier_map = {c.id: c for c in carriers}
        rc_map = {rc.carrier_id: rc for rc in rate_cards}
        ar_map: Dict[int, List[AccessorialRule]] = {}
        for ar in accessorial_rules:
            ar_map.setdefault(ar.carrier_id, []).append(ar)

        # We will generate `count` invoices.
        # Notice: not all shipments must have an invoice (e.g. 20,000 shipments, 15,000 invoices).
        # We also simulate legitimate partials, and injected negative scenarios.
        
        # Scenario allocation:
        # 60% CLEAN (PASS)
        # 8% Scenario 1: BASE_RATE_MISMATCH (overbilled rate)
        # 8% Scenario 2: WEIGHT_DISCREPANCY (overbilled weight)
        # 8% Scenario 3: UNAUTHORIZED_ACCESSORIAL (unperformed liftgate or detention)
        # 8% Scenario 4: DUPLICATE_BILLING (exact duplicate or repeat invoice)
        # 8% Scenario 5: CREDIT_NOTE prepared (and other anomalies)

        scenario_pool = (
            ["NORMAL"] * 60 +
            ["BASE_RATE_MISMATCH"] * 8 +
            ["WEIGHT_DISCREPANCY"] * 8 +
            ["UNAUTHORIZED_ACCESSORIAL"] * 8 +
            ["DUPLICATE_BILLING"] * 8 +
            ["INVALID_CREDIT_NOTE"] * 8
        )

        for i in range(count):
            # Select shipment
            shipment = shipments[i % len(shipments)]
            carrier = carrier_map[shipment.carrier_id]
            rc = rc_map.get(carrier.id)
            rules = ar_map.get(carrier.id, [])

            # Compute true expected calculation
            lane = rc.lanes[0] if rc and rc.lanes else None
            wm = shipment.weight_measurements[0] if shipment.weight_measurements else None
            dr = shipment.delivery_record
            events = shipment.accessorial_events

            calc_result = FreightCalculator.calculate_expected_charges(
                shipment=shipment,
                rate_card=rc,
                rate_lane=lane,
                accessorial_rules=rules,
                weight_measurement=wm,
                delivery_record=dr,
                accessorial_events=events
            )

            # Assign scenario
            scenario = scenario_pool[i % len(scenario_pool)]
            inv_num = f"INV-{carrier.carrier_code}-{100000 + i + 1}"
            inv_date = shipment.delivery_date + timedelta(days=self.rng.randint(2, 10))
            due_date = inv_date + timedelta(days=carrier.payment_terms_days)

            lines_to_create = []
            anomaly_details = {}
            injected_variance = 0.0
            is_anomaly = (scenario != "NORMAL")
            expected_verdict = "FAIL" if is_anomaly else "PASS"

            if scenario == "NORMAL":
                # Matches expected charges exactly (clean invoice)
                for line_idx, exp_item in enumerate(calc_result.line_items):
                    lines_to_create.append({
                        "line_number": line_idx + 1,
                        "charge_type": exp_item.charge_type,
                        "charge_code": exp_item.charge_code,
                        "description": exp_item.description,
                        "billed_units": exp_item.expected_units,
                        "billed_rate": exp_item.expected_rate,
                        "billed_amount": exp_item.expected_amount,
                        "expected_units": exp_item.expected_units,
                        "expected_rate": exp_item.expected_rate,
                        "expected_amount": exp_item.expected_amount,
                        "variance_amount": 0.0,
                        "status": "MATCH"
                    })
                total_billed = calc_result.total_expected_amount

            elif scenario == "BASE_RATE_MISMATCH":
                # Inflate base linehaul rate by 20% to 45%
                markup = round(self.rng.uniform(0.20, 0.45), 2)
                for line_idx, exp_item in enumerate(calc_result.line_items):
                    if exp_item.charge_type == "LINEHAUL":
                        inflated_rate = round(exp_item.expected_rate * (1.0 + markup), 2)
                        inflated_amount = round(exp_item.expected_units * inflated_rate, 2)
                        line_var = round(inflated_amount - exp_item.expected_amount, 2)
                        injected_variance += line_var
                        lines_to_create.append({
                            "line_number": line_idx + 1,
                            "charge_type": exp_item.charge_type,
                            "charge_code": exp_item.charge_code,
                            "description": f"Linehaul (Billed with {markup*100:.0f}% tariff markup)",
                            "billed_units": exp_item.expected_units,
                            "billed_rate": inflated_rate,
                            "billed_amount": inflated_amount,
                            "expected_units": exp_item.expected_units,
                            "expected_rate": exp_item.expected_rate,
                            "expected_amount": exp_item.expected_amount,
                            "variance_amount": line_var,
                            "status": "VARIANCE_DISCREPANCY"
                        })
                        anomaly_details["markup_pct"] = markup
                        anomaly_details["contracted_rate"] = exp_item.expected_rate
                        anomaly_details["billed_rate"] = inflated_rate
                    else:
                        lines_to_create.append({
                            "line_number": line_idx + 1,
                            "charge_type": exp_item.charge_type,
                            "charge_code": exp_item.charge_code,
                            "description": exp_item.description,
                            "billed_units": exp_item.expected_units,
                            "billed_rate": exp_item.expected_rate,
                            "billed_amount": exp_item.expected_amount,
                            "expected_units": exp_item.expected_units,
                            "expected_rate": exp_item.expected_rate,
                            "expected_amount": exp_item.expected_amount,
                            "variance_amount": 0.0,
                            "status": "MATCH"
                        })
                total_billed = round(calc_result.total_expected_amount + injected_variance, 2)

            elif scenario == "WEIGHT_DISCREPANCY":
                # Inflate weight by 30% to 60%
                weight_mult = round(self.rng.uniform(1.30, 1.60), 2)
                for line_idx, exp_item in enumerate(calc_result.line_items):
                    if exp_item.charge_type == "LINEHAUL":
                        inflated_units = round(exp_item.expected_units * weight_mult, 2)
                        inflated_amount = round(inflated_units * exp_item.expected_rate, 2)
                        line_var = round(inflated_amount - exp_item.expected_amount, 2)
                        injected_variance += line_var
                        lines_to_create.append({
                            "line_number": line_idx + 1,
                            "charge_type": exp_item.charge_type,
                            "charge_code": exp_item.charge_code,
                            "description": f"Linehaul (Billed on uncertified re-weigh weight)",
                            "billed_units": inflated_units,
                            "billed_rate": exp_item.expected_rate,
                            "billed_amount": inflated_amount,
                            "expected_units": exp_item.expected_units,
                            "expected_rate": exp_item.expected_rate,
                            "expected_amount": exp_item.expected_amount,
                            "variance_amount": line_var,
                            "status": "VARIANCE_DISCREPANCY"
                        })
                        anomaly_details["certified_weight_cwt"] = exp_item.expected_units
                        anomaly_details["billed_weight_cwt"] = inflated_units
                    else:
                        lines_to_create.append({
                            "line_number": line_idx + 1,
                            "charge_type": exp_item.charge_type,
                            "charge_code": exp_item.charge_code,
                            "description": exp_item.description,
                            "billed_units": exp_item.expected_units,
                            "billed_rate": exp_item.expected_rate,
                            "billed_amount": exp_item.expected_amount,
                            "expected_units": exp_item.expected_units,
                            "expected_rate": exp_item.expected_rate,
                            "expected_amount": exp_item.expected_amount,
                            "variance_amount": 0.0,
                            "status": "MATCH"
                        })
                total_billed = round(calc_result.total_expected_amount + injected_variance, 2)

            elif scenario == "UNAUTHORIZED_ACCESSORIAL":
                # Add unrendered accessorial (e.g. liftgate billed when delivery had dock, or unearned detention)
                unrendered_type = self.rng.choice(["LIFTGATE", "DETENTION", "INSIDE_DELIVERY"])
                fee = 85.0 if unrendered_type == "LIFTGATE" else (150.0 if unrendered_type == "DETENTION" else 75.0)
                injected_variance = fee

                for line_idx, exp_item in enumerate(calc_result.line_items):
                    lines_to_create.append({
                        "line_number": line_idx + 1,
                        "charge_type": exp_item.charge_type,
                        "charge_code": exp_item.charge_code,
                        "description": exp_item.description,
                        "billed_units": exp_item.expected_units,
                        "billed_rate": exp_item.expected_rate,
                        "billed_amount": exp_item.expected_amount,
                        "expected_units": exp_item.expected_units,
                        "expected_rate": exp_item.expected_rate,
                        "expected_amount": exp_item.expected_amount,
                        "variance_amount": 0.0,
                        "status": "MATCH"
                    })

                lines_to_create.append({
                    "line_number": len(lines_to_create) + 1,
                    "charge_type": "ACCESSORIAL",
                    "charge_code": unrendered_type,
                    "description": f"Unauthorized / Unrendered {unrendered_type} Fee",
                    "billed_units": 1.0,
                    "billed_rate": fee,
                    "billed_amount": fee,
                    "expected_units": 0.0,
                    "expected_rate": 0.0,
                    "expected_amount": 0.0,
                    "variance_amount": fee,
                    "status": "UNAUTHORIZED"
                })
                anomaly_details["unauthorized_accessorial_code"] = unrendered_type
                anomaly_details["billed_fee"] = fee
                total_billed = round(calc_result.total_expected_amount + fee, 2)

            elif scenario == "DUPLICATE_BILLING":
                # Clone an earlier generated invoice to simulate genuine duplicate billing
                if invoices:
                    prior_inv = invoices[self.rng.randint(0, len(invoices) - 1)]
                    shipment = prior_inv.shipment or shipment
                    carrier = carrier_map[prior_inv.carrier_id]
                    target_bol = prior_inv.bol_number_billed
                    calc_result = FreightCalculator.calculate_expected_charges(
                        shipment=shipment,
                        rate_card=rc_map.get(carrier.id),
                        rate_lane=rc_map.get(carrier.id).lanes[0] if rc_map.get(carrier.id) and rc_map.get(carrier.id).lanes else None,
                        accessorial_rules=ar_map.get(carrier.id, []),
                        weight_measurement=shipment.weight_measurements[0] if shipment.weight_measurements else None,
                        delivery_record=shipment.delivery_record,
                        accessorial_events=shipment.accessorial_events
                    )
                else:
                    target_bol = shipment.bol_number

                for line_idx, exp_item in enumerate(calc_result.line_items):
                    lines_to_create.append({
                        "line_number": line_idx + 1,
                        "charge_type": exp_item.charge_type,
                        "charge_code": exp_item.charge_code,
                        "description": exp_item.description,
                        "billed_units": exp_item.expected_units,
                        "billed_rate": exp_item.expected_rate,
                        "billed_amount": exp_item.expected_amount,
                        "expected_units": exp_item.expected_units,
                        "expected_rate": exp_item.expected_rate,
                        "expected_amount": exp_item.expected_amount,
                        "variance_amount": 0.0,
                        "status": "MATCH"
                    })
                total_billed = calc_result.total_expected_amount
                injected_variance = total_billed
                anomaly_details["duplicate_bol"] = target_bol

            else: # INVALID_CREDIT_NOTE or other anomaly
                # Bill extra uncontracted administrative fee
                extra_fee = round(self.rng.uniform(45.0, 95.0), 2)
                injected_variance = extra_fee
                for line_idx, exp_item in enumerate(calc_result.line_items):
                    lines_to_create.append({
                        "line_number": line_idx + 1,
                        "charge_type": exp_item.charge_type,
                        "charge_code": exp_item.charge_code,
                        "description": exp_item.description,
                        "billed_units": exp_item.expected_units,
                        "billed_rate": exp_item.expected_rate,
                        "billed_amount": exp_item.expected_amount,
                        "expected_units": exp_item.expected_units,
                        "expected_rate": exp_item.expected_rate,
                        "expected_amount": exp_item.expected_amount,
                        "variance_amount": 0.0,
                        "status": "MATCH"
                    })
                lines_to_create.append({
                    "line_number": len(lines_to_create) + 1,
                    "charge_type": "MISC",
                    "charge_code": "ADMIN_FEE",
                    "description": "Uncontracted Administrative Processing Charge",
                    "billed_units": 1.0,
                    "billed_rate": extra_fee,
                    "billed_amount": extra_fee,
                    "expected_units": 0.0,
                    "expected_rate": 0.0,
                    "expected_amount": 0.0,
                    "variance_amount": extra_fee,
                    "status": "UNAUTHORIZED"
                })
                anomaly_details["uncontracted_misc_fee"] = extra_fee
                total_billed = round(calc_result.total_expected_amount + extra_fee, 2)

            fingerprint = InvoiceValidator.compute_invoice_fingerprint(
                carrier.id, shipment.bol_number, total_billed
            )

            inv = InvoiceHeader(
                invoice_number=inv_num,
                carrier_id=carrier.id,
                shipment_id=shipment.id,
                bol_number_billed=shipment.bol_number,
                invoice_date=inv_date,
                due_date=due_date,
                currency="USD",
                total_billed_amount=total_billed,
                calculated_expected_amount=calc_result.total_expected_amount,
                total_variance_amount=round(total_billed - calc_result.total_expected_amount, 2),
                status="PENDING_AUDIT",
                fingerprint_hash=fingerprint,
                is_duplicate=(scenario == "DUPLICATE_BILLING")
            )
            db.add(inv)
            db.flush()

            for line_data in lines_to_create:
                inv_line = InvoiceLine(
                    invoice_id=inv.id,
                    line_number=line_data["line_number"],
                    charge_type=line_data["charge_type"],
                    charge_code=line_data["charge_code"],
                    description=line_data["description"],
                    billed_units=line_data["billed_units"],
                    billed_rate=line_data["billed_rate"],
                    billed_amount=line_data["billed_amount"],
                    expected_units=line_data["expected_units"],
                    expected_rate=line_data["expected_rate"],
                    expected_amount=line_data["expected_amount"],
                    variance_amount=line_data["variance_amount"],
                    status=line_data["status"]
                )
                db.add(inv_line)

            # Store Ground Truth Label independently
            gt_label = GroundTruthLabel(
                invoice_id=inv.id,
                invoice_number=inv.invoice_number,
                bol_number=shipment.bol_number,
                carrier_code=carrier.carrier_code,
                scenario_type=scenario,
                is_anomaly=is_anomaly,
                expected_verdict=expected_verdict,
                ground_truth_billed=total_billed,
                ground_truth_expected=calc_result.total_expected_amount,
                injected_variance=injected_variance,
                anomaly_details_json=json.dumps(anomaly_details)
            )
            db.add(gt_label)

            invoices.append(inv)
            ground_truths.append(gt_label)

        db.flush()
        return invoices, ground_truths

    def _generate_credit_notes(self, db: Session, carriers: List[Carrier], invoices: List[InvoiceHeader]) -> List[CreditNote]:
        credit_notes = []
        # Find invoices with positive variance (overbilled)
        overbilled = [inv for inv in invoices if inv.total_variance_amount > 5.0]

        for idx, inv in enumerate(overbilled[:len(overbilled)]):
            is_valid_credit = (idx % 2 == 0)
            cn_number = f"CN-{inv.invoice_number.replace('INV-', '')}"

            if is_valid_credit:
                # Legitimate credit note covering full or partial overbilling
                credit_amt = round(inv.total_variance_amount, 2)
                cn = CreditNote(
                    credit_note_number=cn_number,
                    carrier_id=inv.carrier_id,
                    original_invoice_id=inv.id,
                    issue_date=inv.invoice_date + timedelta(days=14),
                    credit_amount=credit_amt,
                    applied_amount=0.0,
                    remaining_balance=credit_amt,
                    status="UNAPPLIED",
                    reason_code="RATE_CORRECTION"
                )
            else:
                # Scenario 5 Anomaly: Excessive credit note or wrong amount
                credit_amt = round(inv.total_variance_amount * 2.5 + 100.0, 2)
                cn = CreditNote(
                    credit_note_number=cn_number,
                    carrier_id=inv.carrier_id,
                    original_invoice_id=inv.id,
                    issue_date=inv.invoice_date + timedelta(days=14),
                    credit_amount=credit_amt,
                    applied_amount=0.0,
                    remaining_balance=credit_amt,
                    status="UNAPPLIED",
                    reason_code="EXCESSIVE_CLAIM"
                )

            db.add(cn)
            credit_notes.append(cn)

        db.flush()
        return credit_notes
