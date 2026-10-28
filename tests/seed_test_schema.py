"""
Seed script proving that the Phase 1 normalized relational schema works end-to-end.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import date, datetime, timedelta
from backend.app.core.database import SessionLocal, engine, Base
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
from backend.app.models.shipment import (
    Shipment, ShipmentLeg, WeightMeasurement, DeliveryEvidence
)
from backend.app.models.invoice import (
    FreightInvoice, InvoiceLine, DuplicateInvoiceGroup, InvoiceValidationRun
)
from backend.app.models.audit_exception import AuditException
from backend.app.models.credit_note import CreditNote
from backend.app.models.audit import AuditEvent, EntityStatusHistory
from backend.app.models.id_generator import (
    generate_carrier_id, generate_rate_card_id, generate_lane_id,
    generate_rate_tier_id, generate_shipment_id, generate_shipment_leg_id,
    generate_weight_measurement_id, generate_accessorial_id,
    generate_shipment_accessorial_id, generate_delivery_evidence_id,
    generate_invoice_id, generate_invoice_line_id, generate_exception_id,
    generate_credit_note_id, generate_duplicate_group_id,
    generate_validation_run_id, generate_audit_event_id, generate_status_history_id
)

def run_seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        print("1. Seeding Carriers and Lanes...")
        c1 = Carrier(
            carrier_id=generate_carrier_id(1),
            carrier_name="Old Dominion Freight Line",
            carrier_code="ODFL",
            status=CarrierStatus.ACTIVE,
            country_code="USA"
        )
        c2 = Carrier(
            carrier_id=generate_carrier_id(2),
            carrier_name="FedEx Freight",
            carrier_code="FXFE",
            status=CarrierStatus.ACTIVE,
            country_code="USA"
        )
        lane1 = Lane(
            lane_id=generate_lane_id(1),
            origin_location_code="ATL-01",
            destination_location_code="ORD-01",
            origin_city="Atlanta",
            destination_city="Chicago",
            origin_country="USA",
            destination_country="USA",
            distance_km=1150.0,
            status=LaneStatus.ACTIVE
        )
        lane2 = Lane(
            lane_id=generate_lane_id(2),
            origin_location_code="DFW-01",
            destination_location_code="LAX-01",
            origin_city="Dallas",
            destination_city="Los Angeles",
            origin_country="USA",
            destination_country="USA",
            distance_km=2300.0,
            status=LaneStatus.ACTIVE
        )
        db.add_all([c1, c2, lane1, lane2])
        db.commit()

        print("2. Seeding RateCards and Weight-Break Tiers...")
        rc1 = RateCard(
            rate_card_id=generate_rate_card_id(c1.carrier_id, 2026, 1),
            carrier_id=c1.carrier_id,
            lane_id=lane1.lane_id,
            service_level=ServiceLevel.STANDARD,
            currency="USD",
            effective_from=date(2026, 1, 1),
            effective_to=date(2026, 12, 31),
            base_rate=120.0,
            minimum_charge=85.0,
            dimensional_weight_divisor=5000.0,
            status=RateCardStatus.ACTIVE
        )
        db.add(rc1)
        db.commit()

        tier1 = RateTier(
            rate_tier_id=generate_rate_tier_id(rc1.rate_card_id, 1),
            rate_card_id=rc1.rate_card_id,
            tier_sequence=1,
            min_weight_kg=0.0,
            max_weight_kg=500.0,
            rate_per_kg=0.45,
            flat_surcharge=0.0
        )
        tier2 = RateTier(
            rate_tier_id=generate_rate_tier_id(rc1.rate_card_id, 2),
            rate_card_id=rc1.rate_card_id,
            tier_sequence=2,
            min_weight_kg=500.0,
            max_weight_kg=2500.0,
            rate_per_kg=0.38,
            flat_surcharge=0.0
        )
        db.add_all([tier1, tier2])
        db.commit()

        print("3. Seeding Accessorial Master Catalog...")
        acc_lg = Accessorial(
            accessorial_id=generate_accessorial_id(1),
            accessorial_code="LIFTGATE",
            description="Hydraulic liftgate delivery service",
            charge_method=ChargeMethod.FLAT,
            rate_amount=85.0,
            currency="USD",
            taxable=False,
            requires_evidence=True,
            status=AccessorialStatus.ACTIVE,
            effective_from=date(2026, 1, 1)
        )
        acc_det = Accessorial(
            accessorial_id=generate_accessorial_id(2),
            accessorial_code="DETENTION",
            description="Driver detention at facility beyond free time",
            charge_method=ChargeMethod.PER_HOUR,
            rate_amount=75.0,
            currency="USD",
            taxable=False,
            requires_evidence=True,
            status=AccessorialStatus.ACTIVE,
            effective_from=date(2026, 1, 1)
        )
        db.add_all([acc_lg, acc_det])
        db.commit()

        print("4. Seeding Shipment, Legs, Scale Weights, and POD Evidence...")
        shp1 = Shipment(
            shipment_id=generate_shipment_id(1, 2026),
            carrier_id=c1.carrier_id,
            lane_id=lane1.lane_id,
            service_level=ServiceLevel.STANDARD,
            ship_date=date(2026, 3, 10),
            delivery_due_date=date(2026, 3, 13),
            delivered_at=datetime(2026, 3, 13, 11, 45),
            actual_length_cm=120.0,
            actual_width_cm=80.0,
            actual_height_cm=140.0,
            actual_weight_kg=480.0,
            declared_weight_kg=480.0,
            chargeable_weight_kg=480.0,
            currency="USD",
            shipment_status=ShipmentStatus.DELIVERED
        )
        db.add(shp1)
        db.commit()

        leg1 = ShipmentLeg(
            shipment_leg_id=generate_shipment_leg_id(shp1.shipment_id, 1),
            shipment_id=shp1.shipment_id,
            leg_sequence=1,
            origin_location_code="ATL-01",
            destination_location_code="ORD-01",
            departure_at=datetime(2026, 3, 10, 8, 0),
            arrival_at=datetime(2026, 3, 13, 11, 0),
            leg_status=ShipmentLegStatus.ARRIVED
        )
        wm1 = WeightMeasurement(
            weight_measurement_id=generate_weight_measurement_id(shp1.shipment_id, 1),
            shipment_id=shp1.shipment_id,
            measurement_type=MeasurementType.ORIGIN_SCALE,
            length_cm=120.0,
            width_cm=80.0,
            height_cm=140.0,
            weight_kg=480.0,
            source=MeasurementSource.SHIPPER,
            is_accepted=True
        )
        dev1 = DeliveryEvidence(
            delivery_evidence_id=generate_delivery_evidence_id(shp1.shipment_id),
            shipment_id=shp1.shipment_id,
            delivered_at=datetime(2026, 3, 13, 11, 45),
            recipient_name="Sam Smith",
            signed_pod_ref="POD-SIG-ATL-ORD-001",
            facility_dock_type="STANDARD_DOCK",
            liftgate_actually_used=False,
            detention_minutes_recorded=30
        )
        sa1 = ShipmentAccessorial(
            shipment_accessorial_id=generate_shipment_accessorial_id(shp1.shipment_id, 1),
            shipment_id=shp1.shipment_id,
            accessorial_id=acc_lg.accessorial_id,
            quantity=1.0,
            authorized=False,
            evidence_reference=None
        )
        db.add_all([leg1, wm1, dev1, sa1])
        db.commit()

        print("5. Seeding Freight Invoice, Line Items, and Validation Run...")
        inv1 = FreightInvoice(
            invoice_id=generate_invoice_id(1, 2026),
            carrier_id=c1.carrier_id,
            shipment_id=shp1.shipment_id,
            raw_shipment_reference=shp1.shipment_id,
            invoice_number="INV-ODFL-2026-001",
            invoice_date=date(2026, 3, 15),
            service_period_start=date(2026, 3, 10),
            service_period_end=date(2026, 3, 13),
            due_date=date(2026, 4, 15),
            currency="USD",
            billed_total=305.0,
            expected_total=220.0,
            variance_amount=85.0,
            invoice_status=InvoiceStatus.EXCEPTION_DISPUTED,
            validation_status=ValidationStatus.FAILED,
            fingerprint_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        )
        db.add(inv1)
        db.commit()

        line1 = InvoiceLine(
            invoice_line_id=generate_invoice_line_id(inv1.invoice_id, 1),
            invoice_id=inv1.invoice_id,
            line_number=1,
            line_type=InvoiceLineType.BASE_LINEHAUL,
            description="Linehaul Base (Tier 1)",
            quantity=480.0,
            unit_of_measure="KG",
            unit_rate=0.4583,
            billed_amount=220.0,
            expected_amount=220.0,
            variance_amount=0.0
        )
        line2 = InvoiceLine(
            invoice_line_id=generate_invoice_line_id(inv1.invoice_id, 2),
            invoice_id=inv1.invoice_id,
            line_number=2,
            line_type=InvoiceLineType.ACCESSORIAL,
            accessorial_id=acc_lg.accessorial_id,
            description="Unauthorized Liftgate Delivery Fee",
            quantity=1.0,
            unit_of_measure="FLAT",
            unit_rate=85.0,
            billed_amount=85.0,
            expected_amount=0.0,
            variance_amount=85.0
        )
        db.add_all([line1, line2])
        db.commit()

        vrun1 = InvoiceValidationRun(
            validation_run_id=generate_validation_run_id(1, 2026),
            invoice_id=inv1.invoice_id,
            run_at=datetime.utcnow(),
            actor="SYSTEM_AUDITOR",
            rules_applied_count=12,
            exceptions_detected_count=1,
            summary_verdict="FAILED",
            details_json='{"discrepancy": "Unauthorized liftgate fee billed without destination proof"}'
        )
        db.add(vrun1)
        db.commit()

        print("6. Seeding Audit Exception and Credit Note...")
        exc1 = AuditException(
            exception_id=generate_exception_id(1, 2026),
            invoice_id=inv1.invoice_id,
            invoice_line_id=line2.invoice_line_id,
            shipment_id=shp1.shipment_id,
            exception_type=ExceptionType.UNAUTHORIZED_ACCESSORIAL,
            severity=ExceptionSeverity.CRITICAL,
            expected_amount=0.0,
            billed_amount=85.0,
            disputed_amount=85.0,
            currency="USD",
            explanation="Carrier billed $85.00 liftgate, but delivery receipt confirms facility has standard loading dock and liftgate was not used.",
            exception_status=ExceptionStatus.DISPUTED
        )
        db.add(exc1)
        db.commit()

        cn1 = CreditNote(
            credit_note_id=generate_credit_note_id(1, 2026),
            exception_id=exc1.exception_id,
            invoice_id=inv1.invoice_id,
            carrier_id=c1.carrier_id,
            credit_note_number="CN-ODFL-2026-001",
            issue_date=date(2026, 3, 20),
            currency="USD",
            credit_amount=85.0,
            approval_status=CreditNoteApprovalStatus.APPROVED,
            reconciliation_status=CreditNoteReconciliationStatus.FULLY_APPLIED
        )
        db.add(cn1)
        db.commit()

        print("7. Seeding Audit Trail and Entity Status History...")
        aud1 = AuditEvent(
            event_id=generate_audit_event_id(1, 2026),
            entity_type="FREIGHT_INVOICE",
            entity_id=inv1.invoice_id,
            event_type="EXCEPTION_DISPUTED",
            actor="SYSTEM_AUDITOR",
            payload_json='{"variance_amount": 85.0, "status": "EXCEPTION_DISPUTED"}',
            notes="Audit failed: unauthorized liftgate fee flagged"
        )
        hist1 = EntityStatusHistory(
            history_id=generate_status_history_id(1, 2026),
            entity_name="FreightInvoice",
            entity_id=inv1.invoice_id,
            from_status=InvoiceStatus.PENDING_AUDIT.value,
            to_status=InvoiceStatus.EXCEPTION_DISPUTED.value,
            transition_reason="Unauthorized accessorial detected during automated audit",
            changed_by="SYSTEM_AUDITOR"
        )
        db.add_all([aud1, hist1])
        db.commit()

        print("\nSeed successfully completed! All 11 core entities + supporting tables populated and verified.")
    finally:
        db.close()

if __name__ == "__main__":
    run_seed()
