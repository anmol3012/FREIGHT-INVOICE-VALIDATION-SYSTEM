import pytest
from datetime import date, datetime, timedelta
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError

from backend.app.core.database import Base
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
from backend.app.models.lifecycle import (
    validate_shipment_transition, validate_invoice_transition,
    validate_exception_transition, validate_credit_note_transition,
    InvalidStateTransitionError
)
from backend.app.models.id_generator import (
    generate_carrier_id, generate_rate_card_id, generate_lane_id,
    generate_rate_tier_id, generate_shipment_id, generate_shipment_leg_id,
    generate_weight_measurement_id, generate_accessorial_id,
    generate_shipment_accessorial_id, generate_delivery_evidence_id,
    generate_invoice_id, generate_invoice_line_id, generate_exception_id,
    generate_credit_note_id, generate_duplicate_group_id
)

@pytest.fixture
def db_session():
    """In-memory SQLite session with strict foreign key enforcement."""
    engine = create_engine("sqlite:///:memory:")
    
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()

# -------------------------------------------------------------
# 1. Deterministic Identifier Formatting Tests
# -------------------------------------------------------------
def test_deterministic_id_formats():
    c_id = generate_carrier_id(1)
    assert c_id == "CAR-000001"

    rc_id = generate_rate_card_id(c_id, year=2026, version_or_seq=1)
    assert rc_id == "RATE-CAR-000001-2026-01"

    lane_id = generate_lane_id(1)
    assert lane_id == "LANE-000001"

    tier_id = generate_rate_tier_id(rc_id, tier_seq=1)
    assert tier_id == "TIER-RATE-CAR-000001-2026-01-01"

    shp_id = generate_shipment_id(1, year=2026)
    assert shp_id == "SHP-2026-000001"

    leg_id = generate_shipment_leg_id(shp_id, leg_seq=1)
    assert leg_id == "LEG-SHP-2026-000001-01"

    wm_id = generate_weight_measurement_id(shp_id, measurement_seq=1)
    assert wm_id == "WM-SHP-2026-000001-01"

    acc_id = generate_accessorial_id(1)
    assert acc_id == "ACC-000001"

    inv_id = generate_invoice_id(1, year=2026)
    assert inv_id == "FINV-2026-000001"

    line_id = generate_invoice_line_id(inv_id, line_number=1)
    assert line_id == "FLINE-FINV-2026-000001-01"

    exc_id = generate_exception_id(1, year=2026)
    assert exc_id == "FEX-2026-000001"

    cn_id = generate_credit_note_id(1, year=2026)
    assert cn_id == "CN-2026-000001"

# -------------------------------------------------------------
# 2. Master Data & Foreign Key Integrity Tests
# -------------------------------------------------------------
def test_carrier_and_lane_creation(db_session):
    c = Carrier(
        carrier_id="CAR-000001",
        carrier_name="Old Dominion Freight Line",
        carrier_code="ODFL",
        status=CarrierStatus.ACTIVE,
        country_code="USA"
    )
    lane = Lane(
        lane_id="LANE-000001",
        origin_location_code="ATL-01",
        destination_location_code="ORD-01",
        origin_city="Atlanta",
        destination_city="Chicago",
        origin_country="USA",
        destination_country="USA",
        distance_km=1150.0,
        status=LaneStatus.ACTIVE
    )
    db_session.add_all([c, lane])
    db_session.commit()

    assert db_session.query(Carrier).count() == 1
    assert db_session.query(Lane).count() == 1

def test_unique_carrier_code_constraint(db_session):
    c1 = Carrier(
        carrier_id="CAR-000001", carrier_name="Carrier One", carrier_code="ODFL", status=CarrierStatus.ACTIVE
    )
    c2 = Carrier(
        carrier_id="CAR-000002", carrier_name="Carrier Two", carrier_code="ODFL", status=CarrierStatus.ACTIVE
    )
    db_session.add(c1)
    db_session.commit()

    db_session.add(c2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

def test_foreign_key_violation_rate_card(db_session):
    """RateCard cannot reference non-existent carrier or lane."""
    rc = RateCard(
        rate_card_id="RATE-CAR-999999-2026-01",
        carrier_id="CAR-999999", # Does not exist!
        lane_id="LANE-999999",    # Does not exist!
        service_level=ServiceLevel.STANDARD,
        currency="USD",
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
        base_rate=125.0,
        minimum_charge=75.0,
        dimensional_weight_divisor=5000.0,
        status=RateCardStatus.ACTIVE
    )
    db_session.add(rc)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

# -------------------------------------------------------------
# 3. RateCard & RateTier Relationships (1:N)
# -------------------------------------------------------------
def test_rate_card_with_tiers(db_session):
    c = Carrier(carrier_id="CAR-000001", carrier_name="Carrier One", carrier_code="CAR1")
    l = Lane(lane_id="LANE-000001", origin_location_code="ATL", destination_location_code="CHI", origin_city="Atlanta", destination_city="Chicago", distance_km=1100.0)
    db_session.add_all([c, l])
    db_session.commit()

    rc = RateCard(
        rate_card_id="RATE-CAR-000001-2026-01",
        carrier_id=c.carrier_id,
        lane_id=l.lane_id,
        service_level=ServiceLevel.STANDARD,
        currency="USD",
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
        base_rate=50.0,
        minimum_charge=75.0,
        dimensional_weight_divisor=5000.0,
        status=RateCardStatus.ACTIVE
    )
    db_session.add(rc)
    db_session.commit()

    # Add 2 weight tiers
    t1 = RateTier(
        rate_tier_id="TIER-RATE-CAR-000001-2026-01-01",
        rate_card_id=rc.rate_card_id,
        tier_sequence=1,
        min_weight_kg=0.0,
        max_weight_kg=500.0,
        rate_per_kg=0.35
    )
    t2 = RateTier(
        rate_tier_id="TIER-RATE-CAR-000001-2026-01-02",
        rate_card_id=rc.rate_card_id,
        tier_sequence=2,
        min_weight_kg=500.0,
        max_weight_kg=2000.0,
        rate_per_kg=0.28
    )
    db_session.add_all([t1, t2])
    db_session.commit()

    fetched_rc = db_session.query(RateCard).filter_by(rate_card_id=rc.rate_card_id).first()
    assert len(fetched_rc.rate_tiers) == 2
    assert fetched_rc.rate_tiers[0].rate_per_kg == 0.35
    assert fetched_rc.rate_tiers[1].rate_per_kg == 0.28

# -------------------------------------------------------------
# 4. Shipment, Legs, Weights, and Bridge Accessorials
# -------------------------------------------------------------
def test_shipment_complete_relationships(db_session):
    c = Carrier(carrier_id="CAR-000001", carrier_name="Carrier One", carrier_code="CAR1")
    l = Lane(lane_id="LANE-000001", origin_location_code="ATL", destination_location_code="CHI", origin_city="Atlanta", destination_city="Chicago", distance_km=1100.0)
    db_session.add_all([c, l])
    db_session.commit()

    s = Shipment(
        shipment_id="SHP-2026-000001",
        carrier_id=c.carrier_id,
        lane_id=l.lane_id,
        service_level=ServiceLevel.STANDARD,
        ship_date=date(2026, 3, 1),
        delivery_due_date=date(2026, 3, 3),
        actual_length_cm=120.0,
        actual_width_cm=80.0,
        actual_height_cm=100.0,
        actual_weight_kg=450.0,
        declared_weight_kg=450.0,
        chargeable_weight_kg=450.0,
        currency="USD",
        shipment_status=ShipmentStatus.DELIVERED
    )
    db_session.add(s)
    db_session.commit()

    # ShipmentLeg
    leg = ShipmentLeg(
        shipment_leg_id="LEG-SHP-2026-000001-01",
        shipment_id=s.shipment_id,
        leg_sequence=1,
        origin_location_code="ATL",
        destination_location_code="CHI",
        leg_status=ShipmentLegStatus.ARRIVED
    )
    # WeightMeasurement
    wm = WeightMeasurement(
        weight_measurement_id="WM-SHP-2026-000001-01",
        shipment_id=s.shipment_id,
        measurement_type=MeasurementType.ORIGIN_SCALE,
        weight_kg=450.0,
        length_cm=120.0,
        width_cm=80.0,
        height_cm=100.0,
        source=MeasurementSource.SHIPPER,
        is_accepted=True
    )
    # DeliveryEvidence
    dev = DeliveryEvidence(
        delivery_evidence_id="DEV-SHP-2026-000001",
        shipment_id=s.shipment_id,
        delivered_at=datetime(2026, 3, 3, 14, 30),
        recipient_name="John Doe",
        signed_pod_ref="POD-SIG-12345",
        facility_dock_type="STANDARD_DOCK",
        liftgate_actually_used=False,
        detention_minutes_recorded=45
    )
    # Accessorial & ShipmentAccessorial
    acc = Accessorial(
        accessorial_id="ACC-000001",
        accessorial_code="LIFTGATE",
        description="Hydraulic liftgate delivery",
        charge_method=ChargeMethod.FLAT,
        rate_amount=75.0,
        currency="USD",
        effective_from=date(2026, 1, 1)
    )
    db_session.add_all([leg, wm, dev, acc])
    db_session.commit()

    sa = ShipmentAccessorial(
        shipment_accessorial_id="SA-SHP-2026-000001-01",
        shipment_id=s.shipment_id,
        accessorial_id=acc.accessorial_id,
        quantity=1.0,
        authorized=True,
        evidence_reference="POD-SIG-12345"
    )
    db_session.add(sa)
    db_session.commit()

    fetched_s = db_session.query(Shipment).filter_by(shipment_id=s.shipment_id).first()
    assert len(fetched_s.shipment_legs) == 1
    assert len(fetched_s.weight_measurements) == 1
    assert fetched_s.delivery_evidence.recipient_name == "John Doe"
    assert len(fetched_s.shipment_accessorials) == 1
    assert fetched_s.shipment_accessorials[0].accessorial.accessorial_code == "LIFTGATE"

# -------------------------------------------------------------
# 5. Untrusted External Shipment Reference & Referential Integrity
# -------------------------------------------------------------
def test_untrusted_shipment_reference_negative_scenario(db_session):
    """
    The shipment reference must support a deliberately invalid external shipment ID
    in negative test scenarios without violating referential integrity.
    """
    c = Carrier(carrier_id="CAR-000001", carrier_name="Carrier One", carrier_code="CAR1")
    db_session.add(c)
    db_session.commit()

    # Invoice referencing a completely fictitious/untrusted shipment ID
    bogus_ref = "SHP-NON-EXISTENT-999999"
    inv = FreightInvoice(
        invoice_id="FINV-2026-000001",
        carrier_id=c.carrier_id,
        shipment_id=None, # Persist NULL to preserve relational integrity!
        raw_shipment_reference=bogus_ref,
        reference_rejection_reason="External shipment reference does not exist in master records",
        invoice_number="INV-CAR1-001",
        invoice_date=date(2026, 4, 1),
        service_period_start=date(2026, 3, 1),
        service_period_end=date(2026, 3, 31),
        due_date=date(2026, 5, 1),
        currency="USD",
        billed_total=350.0,
        expected_total=0.0,
        variance_amount=350.0,
        invoice_status=InvoiceStatus.PENDING_AUDIT,
        validation_status=ValidationStatus.FAILED
    )
    db_session.add(inv)
    db_session.commit()

    saved_inv = db_session.query(FreightInvoice).filter_by(invoice_id=inv.invoice_id).first()
    assert saved_inv.shipment_id is None
    assert saved_inv.raw_shipment_reference == bogus_ref
    assert "does not exist" in saved_inv.reference_rejection_reason

# -------------------------------------------------------------
# 6. Invoice Lines, Exceptions, and Partial Credit Notes
# -------------------------------------------------------------
def test_invoice_exceptions_and_partial_credit_notes(db_session):
    c = Carrier(carrier_id="CAR-000001", carrier_name="Carrier One", carrier_code="CAR1")
    db_session.add(c)
    db_session.commit()

    inv = FreightInvoice(
        invoice_id="FINV-2026-000002",
        carrier_id=c.carrier_id,
        raw_shipment_reference="SHP-2026-000002",
        invoice_number="INV-CAR1-002",
        invoice_date=date(2026, 4, 1),
        service_period_start=date(2026, 3, 1),
        service_period_end=date(2026, 3, 31),
        due_date=date(2026, 5, 1),
        currency="USD",
        billed_total=500.0,
        expected_total=400.0,
        variance_amount=100.0,
        invoice_status=InvoiceStatus.EXCEPTION_DISPUTED,
        validation_status=ValidationStatus.FAILED
    )
    db_session.add(inv)
    db_session.commit()

    line = InvoiceLine(
        invoice_line_id="FLINE-FINV-2026-000002-01",
        invoice_id=inv.invoice_id,
        line_number=1,
        line_type=InvoiceLineType.BASE_LINEHAUL,
        description="Linehaul Base",
        quantity=1.0,
        unit_rate=500.0,
        billed_amount=500.0,
        expected_amount=400.0,
        variance_amount=100.0
    )
    db_session.add(line)
    db_session.commit()

    exc = AuditException(
        exception_id="FEX-2026-000001",
        invoice_id=inv.invoice_id,
        invoice_line_id=line.invoice_line_id,
        exception_type=ExceptionType.BASE_RATE_MISMATCH,
        severity=ExceptionSeverity.CRITICAL,
        expected_amount=400.0,
        billed_amount=500.0,
        disputed_amount=100.0,
        currency="USD",
        explanation="Billed base linehaul exceeds contracted tariff",
        exception_status=ExceptionStatus.DISPUTED
    )
    db_session.add(exc)
    db_session.commit()

    # Partial Credit Notes (AuditException 1:N CreditNote)
    cn1 = CreditNote(
        credit_note_id="CN-2026-000001",
        exception_id=exc.exception_id,
        invoice_id=inv.invoice_id,
        carrier_id=c.carrier_id,
        credit_note_number="CN-CAR1-01A",
        issue_date=date(2026, 4, 15),
        credit_amount=60.0,
        approval_status=CreditNoteApprovalStatus.APPROVED,
        reconciliation_status=CreditNoteReconciliationStatus.PARTIALLY_APPLIED
    )
    cn2 = CreditNote(
        credit_note_id="CN-2026-000002",
        exception_id=exc.exception_id,
        invoice_id=inv.invoice_id,
        carrier_id=c.carrier_id,
        credit_note_number="CN-CAR1-01B",
        issue_date=date(2026, 4, 20),
        credit_amount=40.0,
        approval_status=CreditNoteApprovalStatus.APPROVED,
        reconciliation_status=CreditNoteReconciliationStatus.FULLY_APPLIED
    )
    db_session.add_all([cn1, cn2])
    db_session.commit()

    fetched_exc = db_session.query(AuditException).filter_by(exception_id=exc.exception_id).first()
    assert len(fetched_exc.credit_notes) == 2
    total_credit = sum(c.credit_amount for c in fetched_exc.credit_notes)
    assert total_credit == 100.0

# -------------------------------------------------------------
# 7. Check Constraints & Positive Boundaries
# -------------------------------------------------------------
def test_check_constraint_negative_weight(db_session):
    c = Carrier(carrier_id="CAR-000001", carrier_name="Carrier One", carrier_code="CAR1")
    l = Lane(lane_id="LANE-000001", origin_location_code="ATL", destination_location_code="CHI", origin_city="Atlanta", destination_city="Chicago", distance_km=1100.0)
    db_session.add_all([c, l])
    db_session.commit()

    # Negative actual weight must violate CheckConstraint
    s = Shipment(
        shipment_id="SHP-2026-000002",
        carrier_id=c.carrier_id,
        lane_id=l.lane_id,
        ship_date=date(2026, 3, 1),
        delivery_due_date=date(2026, 3, 3),
        actual_length_cm=100.0,
        actual_width_cm=100.0,
        actual_height_cm=100.0,
        actual_weight_kg=-50.0, # INVALID!
        declared_weight_kg=100.0,
        chargeable_weight_kg=100.0
    )
    db_session.add(s)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

def test_check_constraint_invalid_effective_dates(db_session):
    c = Carrier(carrier_id="CAR-000001", carrier_name="Carrier One", carrier_code="CAR1")
    l = Lane(lane_id="LANE-000001", origin_location_code="ATL", destination_location_code="CHI", origin_city="Atlanta", destination_city="Chicago", distance_km=1100.0)
    db_session.add_all([c, l])
    db_session.commit()

    # effective_from AFTER effective_to must fail
    rc = RateCard(
        rate_card_id="RATE-CAR-000001-2026-BAD",
        carrier_id=c.carrier_id,
        lane_id=l.lane_id,
        effective_from=date(2026, 12, 31),
        effective_to=date(2026, 1, 1), # INVALID!
        base_rate=50.0,
        minimum_charge=75.0,
        dimensional_weight_divisor=5000.0
    )
    db_session.add(rc)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

# -------------------------------------------------------------
# 8. Lifecycle State Machine Transition Restrictions
# -------------------------------------------------------------
def test_lifecycle_state_machine_validations():
    # Valid shipment progression
    assert validate_shipment_transition(ShipmentStatus.BOOKED, ShipmentStatus.IN_TRANSIT) is True
    assert validate_shipment_transition(ShipmentStatus.IN_TRANSIT, ShipmentStatus.DELIVERED) is True

    # Invalid jump from DELIVERED (terminal)
    with pytest.raises(InvalidStateTransitionError):
        validate_shipment_transition(ShipmentStatus.DELIVERED, ShipmentStatus.BOOKED)

    # Valid invoice progression
    assert validate_invoice_transition(InvoiceStatus.SUBMITTED, InvoiceStatus.PENDING_AUDIT) is True
    assert validate_invoice_transition(InvoiceStatus.PENDING_AUDIT, InvoiceStatus.VALIDATED_MATCH) is True
    assert validate_invoice_transition(InvoiceStatus.VALIDATED_MATCH, InvoiceStatus.PAID) is True

    # Invalid jump: PAID (terminal) cannot transition to PENDING_AUDIT
    with pytest.raises(InvalidStateTransitionError):
        validate_invoice_transition(InvoiceStatus.PAID, InvoiceStatus.PENDING_AUDIT)

    # Valid exception progression
    assert validate_exception_transition(ExceptionStatus.OPEN, ExceptionStatus.UNDER_REVIEW) is True
    assert validate_exception_transition(ExceptionStatus.UNDER_REVIEW, ExceptionStatus.DISPUTED) is True
    assert validate_exception_transition(ExceptionStatus.DISPUTED, ExceptionStatus.AUTO_RESOLVED) is True

    # Invalid jump from AUTO_RESOLVED (terminal)
    with pytest.raises(InvalidStateTransitionError):
        validate_exception_transition(ExceptionStatus.AUTO_RESOLVED, ExceptionStatus.OPEN)
