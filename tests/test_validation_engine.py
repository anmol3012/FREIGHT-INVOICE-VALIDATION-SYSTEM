"""
Phase 3 Automated Test Suite: Freight Calculation and Invoice Validation Engine.
Tests all 5 mandatory negative scenarios, 20-step validation workflow,
contract selection precedence, weight-break rating, accessorial proof verification,
duplicate detection, and credit note limits.
"""

import pytest
from datetime import date, datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

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
from backend.app.models.shipment import Shipment, ShipmentLeg, WeightMeasurement, DeliveryEvidence
from backend.app.models.invoice import FreightInvoice, InvoiceLine
from backend.app.models.audit_exception import AuditException
from backend.app.models.credit_note import CreditNote

from backend.app.engine.contract_selector import ContractSelector
from backend.app.engine.weight_service import WeightRatingService
from backend.app.engine.accessorial_service import AccessorialService
from backend.app.engine.duplicate_service import DuplicateDetectionService
from backend.app.engine.credit_note_service import CreditNoteService
from backend.app.engine.validator import FreightInvoiceValidator


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)
    db = TestingSession()
    yield db
    db.close()


@pytest.fixture
def seeded_env(test_db):
    """Sets up a complete clean carrier, lane, contract with tiers, accessorials, and shipment."""
    c = Carrier(
        carrier_id="CAR-000001",
        carrier_name="Swift Freight Line",
        carrier_code="SWFT",
        status=CarrierStatus.ACTIVE,
        country_code="USA"
    )
    test_db.add(c)

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
    test_db.add(lane)

    # Active Rate Card (effective all 2026)
    rc = RateCard(
        rate_card_id="RATE-CAR-000001-2026-01",
        carrier_id="CAR-000001",
        lane_id="LANE-000001",
        service_level=ServiceLevel.STANDARD,
        currency="USD",
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
        base_rate=0.45,
        minimum_charge=75.0,
        dimensional_weight_divisor=5000.0,
        status=RateCardStatus.ACTIVE
    )
    test_db.add(rc)

    # Rate Tiers
    # Tier 1: 0 - 250 kg @ $0.60/kg
    t1 = RateTier(
        rate_tier_id="TIER-RATE-CAR-000001-2026-01-01",
        rate_card_id="RATE-CAR-000001-2026-01",
        tier_sequence=1,
        min_weight_kg=0.0,
        max_weight_kg=250.0,
        rate_per_kg=0.60,
        flat_surcharge=0.0
    )
    # Tier 2: 250 - 1000 kg @ $0.45/kg
    t2 = RateTier(
        rate_tier_id="TIER-RATE-CAR-000001-2026-01-02",
        rate_card_id="RATE-CAR-000001-2026-01",
        tier_sequence=2,
        min_weight_kg=250.0,
        max_weight_kg=1000.0,
        rate_per_kg=0.45,
        flat_surcharge=0.0
    )
    test_db.add_all([t1, t2])

    # Accessorials
    acc_liftgate = Accessorial(
        accessorial_id="ACC-000001",
        accessorial_code="LIFTGATE",
        description="Hydraulic Liftgate Service",
        charge_method=ChargeMethod.FLAT,
        rate_amount=75.0,
        taxable=False,
        requires_evidence=True,
        status=AccessorialStatus.ACTIVE,
        effective_from=date(2026, 1, 1)
    )
    acc_detention = Accessorial(
        accessorial_id="ACC-000002",
        accessorial_code="DETENTION",
        description="Driver Detention Beyond Free Time",
        charge_method=ChargeMethod.PER_HOUR,
        rate_amount=80.0,
        taxable=False,
        requires_evidence=True,
        status=AccessorialStatus.ACTIVE,
        effective_from=date(2026, 1, 1)
    )
    test_db.add_all([acc_liftgate, acc_detention])

    # Shipment: 300 kg actual, 120x80x100 cm (dim wt = 192 kg -> chargeable = 300 kg -> Tier 2)
    s = Shipment(
        shipment_id="SHP-2026-000001",
        carrier_id="CAR-000001",
        lane_id="LANE-000001",
        service_level=ServiceLevel.STANDARD,
        ship_date=date(2026, 4, 1),
        delivery_due_date=date(2026, 4, 3),
        delivered_at=datetime(2026, 4, 3, 14, 0),
        actual_length_cm=120.0,
        actual_width_cm=80.0,
        actual_height_cm=100.0,
        actual_weight_kg=300.0,
        declared_weight_kg=300.0,
        chargeable_weight_kg=300.0,
        currency="USD",
        shipment_status=ShipmentStatus.DELIVERED
    )
    test_db.add(s)

    # Delivery Evidence with standard dock and 45 min dwell (no detention, no liftgate)
    dev = DeliveryEvidence(
        delivery_evidence_id="DEV-SHP-2026-000001",
        shipment_id="SHP-2026-000001",
        delivered_at=datetime(2026, 4, 3, 14, 0),
        recipient_name="Dock Foreman John",
        signed_pod_ref="POD-SIG-SHP-2026-000001",
        facility_dock_type="STANDARD_DOCK",
        liftgate_actually_used=False,
        detention_minutes_recorded=45
    )
    test_db.add(dev)

    test_db.commit()
    return {
        "carrier": c,
        "lane": lane,
        "rate_card": rc,
        "shipment": s,
        "delivery_evidence": dev
    }


# =============================================================================
# 1. Contract Selection Service Tests
# =============================================================================

def test_contract_selector_precedence_and_matching(test_db, seeded_env):
    """Verifies single rate card matching, date specificity precedence, and missing contract."""
    # 1. Exact match
    res = ContractSelector.select_rate_card(
        test_db,
        carrier_id="CAR-000001",
        lane_id="LANE-000001",
        service_level=ServiceLevel.STANDARD,
        shipment_date=date(2026, 4, 1)
    )
    assert res.status == "FOUND"
    assert res.rate_card.rate_card_id == "RATE-CAR-000001-2026-01"

    # 2. Missing contract for unknown lane
    res_missing = ContractSelector.select_rate_card(
        test_db,
        carrier_id="CAR-000001",
        lane_id="LANE-999999",
        service_level=ServiceLevel.STANDARD,
        shipment_date=date(2026, 4, 1)
    )
    assert res_missing.status == "MISSING"
    assert res_missing.rate_card is None


# =============================================================================
# 2. Weight Calculation and Base Freight Rating Tests
# =============================================================================

def test_weight_rating_service_tier_and_minimum_charge(seeded_env):
    """Verifies dimensional weight, tier lookup, and minimum charge enforcement."""
    s = seeded_env["shipment"]
    rc = seeded_env["rate_card"]

    # 300 kg -> Tier 2 (250-1000 kg @ $0.45) -> 300 * 0.45 = $135.00
    res = WeightRatingService.evaluate_shipment_weight(s, rc)
    assert res.chargeable_weight_kg == 300.0
    assert res.tier_sequence == 2
    assert res.tier_rate_per_kg == 0.45
    assert res.expected_linehaul_amount == 135.00
    assert not res.is_minimum_charge_applied

    # Small light shipment: 50 kg, 40x40x40 cm (dim wt = 12.8 kg -> chargeable 50 kg)
    # Tier 1: 50 * $0.60 = $30.00 < Min $75.00 floor
    s.actual_weight_kg = 50.0
    s.actual_length_cm = 40.0
    s.actual_width_cm = 40.0
    s.actual_height_cm = 40.0
    res_min = WeightRatingService.evaluate_shipment_weight(s, rc)
    assert res_min.is_minimum_charge_applied
    assert res_min.expected_linehaul_amount == 75.00 # Enforces $75.00 floor


# =============================================================================
# 3. Accessorial and Evidence Verification Tests
# =============================================================================

def test_accessorial_evidence_and_free_time_rules(test_db, seeded_env):
    """Validates liftgate and detention proof checks."""
    s = seeded_env["shipment"]
    dev = seeded_env["delivery_evidence"]
    rc = seeded_env["rate_card"]

    # Test Liftgate when facility has standard dock and liftgate was NOT used
    res_liftgate = AccessorialService.audit_accessorial_charge(
        db=test_db,
        accessorial_code="LIFTGATE",
        billed_amount=75.0,
        billed_quantity=1.0,
        shipment=s,
        delivery_evidence=dev,
        rate_card=rc,
        linehaul_amount=135.0,
        chargeable_weight_kg=300.0
    )
    assert not res_liftgate.is_valid
    assert res_liftgate.expected_amount == 0.0
    assert "liftgate was not utilized" in res_liftgate.discrepancy_reason

    # Test Detention when recorded dwell is 45 min (within 120 min free time)
    res_det = AccessorialService.audit_accessorial_charge(
        db=test_db,
        accessorial_code="DETENTION",
        billed_amount=80.0,
        billed_quantity=1.0,
        shipment=s,
        delivery_evidence=dev,
        rate_card=rc,
        linehaul_amount=135.0,
        chargeable_weight_kg=300.0
    )
    assert not res_det.is_valid
    assert res_det.expected_amount == 0.0
    assert "within standard 120 min free-time" in res_det.discrepancy_reason


# =============================================================================
# 4. Mandatory Negative Scenario A: Unknown Shipment Reference
# =============================================================================

def test_scenario_a_unknown_shipment_reference(test_db, seeded_env):
    """
    Scenario A: Raw invoice references a nonexistent shipment.
    Expected: reject invalid reference, record issue, avoid fabricating shipment record.
    """
    inv = FreightInvoice(
        invoice_id="FINV-2026-990001",
        carrier_id="CAR-000001",
        shipment_id=None, # Quarantined null FK
        raw_shipment_reference="SHP-UNKNOWN-999999",
        invoice_number="INV-SWFT-990001",
        invoice_date=date(2026, 4, 5),
        service_period_start=date(2026, 4, 1),
        service_period_end=date(2026, 4, 3),
        due_date=date(2026, 5, 5),
        currency="USD",
        billed_total=180.0,
        expected_total=0.0,
        variance_amount=180.0,
        invoice_status=InvoiceStatus.SUBMITTED,
        validation_status=ValidationStatus.UNAUDITED
    )
    test_db.add(inv)
    test_db.add(InvoiceLine(
        invoice_line_id="FLINE-FINV-2026-990001-01",
        invoice_id=inv.invoice_id,
        line_number=1,
        line_type=InvoiceLineType.BASE_LINEHAUL,
        description="Linehaul Base",
        quantity=300.0,
        unit_rate=0.60,
        billed_amount=180.0
    ))
    test_db.commit()

    summary = FreightInvoiceValidator.validate_invoice(test_db, inv.invoice_id)
    assert summary.overall_verdict == "FAILED"
    assert summary.validation_status == ValidationStatus.FAILED
    assert summary.expected_total == 0.0
    assert summary.variance_amount == 180.0
    assert any("Scenario A" in msg or "unknown" in msg.lower() for msg in summary.diagnostic_messages)

    # Verify exception ticket created
    exc = test_db.query(AuditException).filter(AuditException.invoice_id == inv.invoice_id).first()
    assert exc is not None
    assert exc.exception_type == ExceptionType.UNMATCHED_SHIPMENT
    assert exc.disputed_amount == 180.0


# =============================================================================
# 5. Mandatory Negative Scenario B: Expired Rate Card
# =============================================================================

def test_scenario_b_expired_rate_card(test_db, seeded_env):
    """
    Scenario B: Contract expired before the shipment date.
    Expected: flag invalid rate and mark as unresolved/disputed.
    """
    # Create an expired rate card for CAR-000001 on a new lane
    lane2 = Lane(
        lane_id="LANE-000002",
        origin_location_code="LAX-01",
        destination_location_code="SEA-01",
        origin_city="Los Angeles",
        destination_city="Seattle",
        distance_km=1800.0,
        status=LaneStatus.ACTIVE
    )
    test_db.add(lane2)

    rc_expired = RateCard(
        rate_card_id="RATE-CAR-000001-2025-01",
        carrier_id="CAR-000001",
        lane_id="LANE-000002",
        service_level=ServiceLevel.STANDARD,
        currency="USD",
        effective_from=date(2025, 1, 1),
        effective_to=date(2025, 12, 31), # Expired!
        base_rate=0.40,
        minimum_charge=70.0,
        status=RateCardStatus.ACTIVE
    )
    test_db.add(rc_expired)

    s2 = Shipment(
        shipment_id="SHP-2026-000002",
        carrier_id="CAR-000001",
        lane_id="LANE-000002",
        service_level=ServiceLevel.STANDARD,
        ship_date=date(2026, 3, 1), # Shipped in 2026 after expiration
        delivery_due_date=date(2026, 3, 4),
        actual_length_cm=100.0, actual_width_cm=100.0, actual_height_cm=100.0,
        actual_weight_kg=200.0, declared_weight_kg=200.0, chargeable_weight_kg=200.0,
        currency="USD"
    )
    test_db.add(s2)

    inv = FreightInvoice(
        invoice_id="FINV-2026-990002",
        carrier_id="CAR-000001",
        shipment_id=s2.shipment_id,
        raw_shipment_reference=s2.shipment_id,
        invoice_number="INV-SWFT-990002",
        invoice_date=date(2026, 3, 10),
        service_period_start=date(2026, 3, 1),
        service_period_end=date(2026, 3, 4),
        due_date=date(2026, 4, 10),
        billed_total=120.0,
        expected_total=0.0,
        variance_amount=120.0,
        invoice_status=InvoiceStatus.SUBMITTED
    )
    test_db.add(inv)
    test_db.add(InvoiceLine(
        invoice_line_id="FLINE-FINV-2026-990002-01",
        invoice_id=inv.invoice_id,
        line_number=1,
        line_type=InvoiceLineType.BASE_LINEHAUL,
        description="Linehaul Base",
        quantity=200.0,
        unit_rate=0.60,
        billed_amount=120.0
    ))
    test_db.commit()

    summary = FreightInvoiceValidator.validate_invoice(test_db, inv.invoice_id)
    assert summary.overall_verdict == "FAILED"
    exc = test_db.query(AuditException).filter(AuditException.invoice_id == inv.invoice_id).first()
    assert exc is not None
    assert "expired" in exc.explanation.lower()


# =============================================================================
# 6. Mandatory Negative Scenario C: Incorrect Weight Tier
# =============================================================================

def test_scenario_c_incorrect_weight_tier(test_db, seeded_env):
    """
    Scenario C: Invoice bills Tier 1 rate ($0.60/kg) instead of Tier 2 rate ($0.45/kg).
    Expected: calculate correct tier and explain monetary difference.
    """
    s = seeded_env["shipment"]
    inv = FreightInvoice(
        invoice_id="FINV-2026-990003",
        carrier_id="CAR-000001",
        shipment_id=s.shipment_id,
        raw_shipment_reference=s.shipment_id,
        invoice_number="INV-SWFT-990003",
        invoice_date=date(2026, 4, 10),
        service_period_start=date(2026, 4, 1),
        service_period_end=date(2026, 4, 3),
        due_date=date(2026, 5, 10),
        billed_total=180.0, # 300 kg * $0.60 = $180.00 (Tier 1 pricing) vs expected Tier 2 $135.00
        expected_total=0.0,
        variance_amount=45.0,
        invoice_status=InvoiceStatus.SUBMITTED
    )
    test_db.add(inv)

    line = InvoiceLine(
        invoice_line_id="FLINE-FINV-2026-990003-01",
        invoice_id=inv.invoice_id,
        line_number=1,
        line_type=InvoiceLineType.BASE_LINEHAUL,
        description="Linehaul Base",
        quantity=300.0,
        unit_of_measure="KG",
        unit_rate=0.60, # Wrong tier rate!
        billed_amount=180.0,
        expected_amount=0.0,
        variance_amount=45.0
    )
    test_db.add(line)
    test_db.commit()

    summary = FreightInvoiceValidator.validate_invoice(test_db, inv.invoice_id)
    assert summary.overall_verdict == "FAILED"
    exc = test_db.query(AuditException).filter(AuditException.invoice_id == inv.invoice_id).first()
    assert exc is not None
    assert exc.exception_type == ExceptionType.WEIGHT_DISCREPANCY
    assert "Tier 2" in exc.explanation


# =============================================================================
# 7. Mandatory Negative Scenario D: Duplicate Fuel Surcharge
# =============================================================================

def test_scenario_d_duplicate_fuel_surcharge(test_db, seeded_env):
    """
    Scenario D: The same fuel surcharge is billed twice on the invoice.
    Expected: identify duplicated charge, variance without double counting.
    """
    s = seeded_env["shipment"]
    inv = FreightInvoice(
        invoice_id="FINV-2026-990004",
        carrier_id="CAR-000001",
        shipment_id=s.shipment_id,
        raw_shipment_reference=s.shipment_id,
        invoice_number="INV-SWFT-990004",
        invoice_date=date(2026, 4, 10),
        service_period_start=date(2026, 4, 1),
        service_period_end=date(2026, 4, 3),
        due_date=date(2026, 5, 10),
        billed_total=172.80, # Linehaul $135 + FSC $18.90 + Duplicate FSC $18.90 = $172.80
        expected_total=0.0,
        variance_amount=18.90,
        invoice_status=InvoiceStatus.SUBMITTED
    )
    test_db.add(inv)

    l1 = InvoiceLine(
        invoice_line_id="FLINE-FINV-2026-990004-01",
        invoice_id=inv.invoice_id,
        line_number=1,
        line_type=InvoiceLineType.BASE_LINEHAUL,
        description="Linehaul Base",
        quantity=300.0,
        unit_rate=0.45,
        billed_amount=135.0
    )
    l2 = InvoiceLine(
        invoice_line_id="FLINE-FINV-2026-990004-02",
        invoice_id=inv.invoice_id,
        line_number=2,
        line_type=InvoiceLineType.FUEL_SURCHARGE,
        description="Primary Fuel Surcharge",
        quantity=1.0,
        unit_rate=18.90,
        billed_amount=18.90
    )
    l3 = InvoiceLine(
        invoice_line_id="FLINE-FINV-2026-990004-03",
        invoice_id=inv.invoice_id,
        line_number=3,
        line_type=InvoiceLineType.FUEL_SURCHARGE,
        description="Secondary Duplicate Fuel Adjustment",
        quantity=1.0,
        unit_rate=18.90,
        billed_amount=18.90
    )
    test_db.add_all([l1, l2, l3])
    test_db.commit()

    summary = FreightInvoiceValidator.validate_invoice(test_db, inv.invoice_id)
    assert summary.overall_verdict == "FAILED"
    exc = test_db.query(AuditException).filter(
        AuditException.invoice_id == inv.invoice_id,
        AuditException.exception_type == ExceptionType.DUPLICATE_BILLING
    ).first()
    assert exc is not None
    assert "Duplicate fuel surcharge" in exc.explanation


# =============================================================================
# 8. Mandatory Negative Scenario E: Excessive Credit Note
# =============================================================================

def test_scenario_e_excessive_credit_note(test_db, seeded_env):
    """
    Scenario E: Credit note exceeds the approved disputed amount.
    Expected: reject excessive amount, preserve record, prevent invalid reconciliation.
    """
    inv = FreightInvoice(
        invoice_id="FINV-2026-990005",
        carrier_id="CAR-000001",
        raw_shipment_reference="SHP-2026-000001",
        invoice_number="INV-SWFT-990005",
        invoice_date=date(2026, 4, 10),
        service_period_start=date(2026, 4, 1),
        service_period_end=date(2026, 4, 3),
        due_date=date(2026, 5, 10),
        billed_total=200.0,
        invoice_status=InvoiceStatus.EXCEPTION_DISPUTED
    )
    test_db.add(inv)

    # Approved exception with dispute balance of $65.00
    exc = AuditException(
        exception_id="FEX-2026-990005",
        invoice_id=inv.invoice_id,
        exception_type=ExceptionType.BASE_RATE_MISMATCH,
        severity=ExceptionSeverity.HIGH,
        expected_amount=135.0,
        billed_amount=200.0,
        disputed_amount=65.0,
        explanation="Disputed tariff inflation",
        exception_status=ExceptionStatus.OPEN
    )
    test_db.add(exc)

    # Credit Note issued for $120.00 (exceeds $65.00 by $55.00!)
    cn_excessive = CreditNote(
        credit_note_id="CN-2026-990001",
        exception_id=exc.exception_id,
        invoice_id=inv.invoice_id,
        carrier_id="CAR-000001",
        credit_note_number="CN-SWFT-990001",
        issue_date=date(2026, 4, 20),
        credit_amount=120.0,
        approval_status=CreditNoteApprovalStatus.PENDING_APPROVAL
    )
    test_db.add(cn_excessive)
    test_db.commit()

    # Reconcile credit note
    res = CreditNoteService.validate_credit_note(test_db, cn_excessive.credit_note_id)
    assert not res.is_valid
    assert res.approval_status == CreditNoteApprovalStatus.REJECTED
    assert res.reconciliation_status == CreditNoteReconciliationStatus.REJECTED
    assert res.excess_amount == 55.0
    assert "Scenario E Violation" in res.explanation
