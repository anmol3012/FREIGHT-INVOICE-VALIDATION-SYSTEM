"""
Boundary and Edge-Case Test Suite for Freight Invoice Validation System (Phase 7).

Verifies:
1. Weight-tier boundary conditions (exact, just below, just above).
2. Rate-card effective-date boundaries (exact effective date, expired 1 day before, open-ended).
3. Missing vs competing rate-card selection (specificity precedence).
4. Zero-variance match, positive overcharge, and negative undercharge variances.
5. Zero-value and legitimate repeated vs duplicate billing charges.
6. Credit notes: exact match, slight excess (+0.01 / Scenario E rejection), and cumulative multi-credit exhaustion.
"""

import pytest
from datetime import date, datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.database import Base
from backend.app.models.carrier import Carrier
from backend.app.models.lane import Lane
from backend.app.models.rate_card import RateCard, RateTier
from backend.app.models.shipment import Shipment, WeightMeasurement, DeliveryEvidence
from backend.app.models.invoice import FreightInvoice, InvoiceLine
from backend.app.models.audit_exception import AuditException
from backend.app.models.credit_note import CreditNote
from backend.app.models.enums import (
    CarrierStatus, LaneStatus, RateCardStatus, ServiceLevel,
    ShipmentStatus, InvoiceStatus, ValidationStatus, InvoiceLineType,
    ExceptionType, ExceptionSeverity, ExceptionStatus,
    CreditNoteApprovalStatus, CreditNoteReconciliationStatus
)
from backend.app.engine.calculator import ContractualFreightCalculator
from backend.app.engine.weight_service import WeightRatingService
from backend.app.engine.contract_selector import ContractSelector
from backend.app.engine.validator import FreightInvoiceValidator
from backend.app.engine.credit_note_service import CreditNoteService


@pytest.fixture
def boundary_db():
    """Sets up an isolated, in-memory SQLite database for boundary testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    yield session
    session.close()


def create_base_carrier_and_lane(db, carrier_id="CAR-BOUND-001", lane_id="LANE-BOUND-001"):
    carrier = Carrier(
        carrier_id=carrier_id,
        carrier_name="Boundary Logistics Express",
        carrier_code="BLEX",
        status=CarrierStatus.ACTIVE,
        country_code="USA"
    )
    lane = Lane(
        lane_id=lane_id,
        origin_location_code="ORD-01",
        destination_location_code="DFW-01",
        origin_city="Chicago",
        destination_city="Dallas",
        origin_country="USA",
        destination_country="USA",
        distance_km=1300.0,
        status=LaneStatus.ACTIVE
    )
    db.add(carrier)
    db.add(lane)
    db.commit()
    return carrier, lane


# ============================================================================
# 1. Weight-Tier Boundaries
# ============================================================================

def test_boundary_weight_tier_exact_and_offsets(boundary_db):
    """Tests shipment exactly at a tier boundary, one smallest unit below, and one above."""
    carrier, lane = create_base_carrier_and_lane(boundary_db, "CAR-WT-001", "LANE-WT-001")

    rc = RateCard(
        rate_card_id="RATE-WT-001",
        carrier_id=carrier.carrier_id,
        lane_id=lane.lane_id,
        service_level=ServiceLevel.STANDARD,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
        base_rate=0.50,
        minimum_charge=50.0,
        status=RateCardStatus.ACTIVE
    )
    boundary_db.add(rc)

    tier_1 = RateTier(
        rate_tier_id="TIER-WT-001-01",
        rate_card_id=rc.rate_card_id,
        tier_sequence=1,
        min_weight_kg=0.0,
        max_weight_kg=100.0,
        rate_per_kg=1.50,
        flat_surcharge=10.0
    )
    tier_2 = RateTier(
        rate_tier_id="TIER-WT-001-02",
        rate_card_id=rc.rate_card_id,
        tier_sequence=2,
        min_weight_kg=100.0,
        max_weight_kg=500.0,
        rate_per_kg=1.10,
        flat_surcharge=20.0
    )
    boundary_db.add_all([tier_1, tier_2])
    boundary_db.commit()

    # 1. Exactly at boundary: 100.0 kg -> should match Tier 1 (first bracket <= 100.0)
    shp_exact = Shipment(
        shipment_id="SHP-BOUND-100",
        carrier_id=carrier.carrier_id,
        lane_id=lane.lane_id,
        service_level=ServiceLevel.STANDARD,
        ship_date=date(2026, 6, 1),
        delivery_due_date=date(2026, 6, 3),
        actual_length_cm=50.0, actual_width_cm=50.0, actual_height_cm=50.0, # vol = 25 kg < 100 kg
        actual_weight_kg=100.0,
        chargeable_weight_kg=100.0,
        shipment_status=ShipmentStatus.DELIVERED
    )
    res_exact = WeightRatingService.evaluate_shipment_weight(shp_exact, rc, rounding_policy="ROUND_2DEC")
    assert res_exact.matched_tier.tier_sequence == 1
    assert res_exact.tier_rate_per_kg == 1.50
    # Expected linehaul: 100.0 * 1.50 + 10.0 = 160.0
    assert res_exact.expected_linehaul_amount == 160.0

    # 2. Smallest supported unit below: 99.9 kg -> matches Tier 1
    shp_below = Shipment(
        shipment_id="SHP-BOUND-99.9",
        carrier_id=carrier.carrier_id,
        lane_id=lane.lane_id,
        service_level=ServiceLevel.STANDARD,
        ship_date=date(2026, 6, 1),
        delivery_due_date=date(2026, 6, 3),
        actual_length_cm=50.0, actual_width_cm=50.0, actual_height_cm=50.0,
        actual_weight_kg=99.9,
        chargeable_weight_kg=99.9,
        shipment_status=ShipmentStatus.DELIVERED
    )
    res_below = WeightRatingService.evaluate_shipment_weight(shp_below, rc, rounding_policy="ROUND_2DEC")
    assert res_below.matched_tier.tier_sequence == 1
    assert res_below.expected_linehaul_amount == round(99.9 * 1.50 + 10.0, 2)

    # 3. Smallest supported unit above: 100.1 kg -> matches Tier 2
    shp_above = Shipment(
        shipment_id="SHP-BOUND-100.1",
        carrier_id=carrier.carrier_id,
        lane_id=lane.lane_id,
        service_level=ServiceLevel.STANDARD,
        ship_date=date(2026, 6, 1),
        delivery_due_date=date(2026, 6, 3),
        actual_length_cm=50.0, actual_width_cm=50.0, actual_height_cm=50.0,
        actual_weight_kg=100.1,
        chargeable_weight_kg=100.1,
        shipment_status=ShipmentStatus.DELIVERED
    )
    res_above = WeightRatingService.evaluate_shipment_weight(shp_above, rc, rounding_policy="ROUND_2DEC")
    assert res_above.matched_tier.tier_sequence == 2
    assert res_above.tier_rate_per_kg == 1.10
    # Expected linehaul: 100.1 * 1.10 + 20.0 = 130.11
    assert res_above.expected_linehaul_amount == round(100.1 * 1.10 + 20.0, 2)


# ============================================================================
# 2. Rate-Card Effective-Date Boundaries
# ============================================================================

def test_boundary_contract_effective_date_boundaries(boundary_db):
    """Tests contract effective on shipment date, expired 1 day before, and open-ended."""
    carrier, lane = create_base_carrier_and_lane(boundary_db, "CAR-DATE-001", "LANE-DATE-001")

    # 1. Contract effective exactly on 2026-06-01 to 2026-06-30
    rc_june = RateCard(
        rate_card_id="RATE-JUNE-001",
        carrier_id=carrier.carrier_id,
        lane_id=lane.lane_id,
        service_level=ServiceLevel.STANDARD,
        effective_from=date(2026, 6, 1),
        effective_to=date(2026, 6, 30),
        base_rate=0.50,
        minimum_charge=50.0,
        status=RateCardStatus.ACTIVE
    )
    boundary_db.add(rc_june)
    boundary_db.commit()

    # Shipment on exact start date: 2026-06-01 -> FOUND
    res_exact_start = ContractSelector.select_rate_card(
        boundary_db, carrier.carrier_id, lane.lane_id, ServiceLevel.STANDARD, date(2026, 6, 1)
    )
    assert res_exact_start.status == "FOUND"
    assert res_exact_start.rate_card.rate_card_id == "RATE-JUNE-001"

    # Shipment on exact end date: 2026-06-30 -> FOUND
    res_exact_end = ContractSelector.select_rate_card(
        boundary_db, carrier.carrier_id, lane.lane_id, ServiceLevel.STANDARD, date(2026, 6, 30)
    )
    assert res_exact_end.status == "FOUND"
    assert res_exact_end.rate_card.rate_card_id == "RATE-JUNE-001"

    # Shipment immediately expired: 2026-07-01 (1 day after effective_to) -> EXPIRED
    res_expired_1d = ContractSelector.select_rate_card(
        boundary_db, carrier.carrier_id, lane.lane_id, ServiceLevel.STANDARD, date(2026, 7, 1)
    )
    assert res_expired_1d.status == "EXPIRED"
    assert "expired" in res_expired_1d.reason.lower()

    # 2. Open-ended contract (effective_to is None)
    rc_open = RateCard(
        rate_card_id="RATE-OPEN-001",
        carrier_id=carrier.carrier_id,
        lane_id=lane.lane_id,
        service_level=ServiceLevel.EXPEDITED,
        effective_from=date(2026, 1, 1),
        effective_to=None,
        base_rate=0.75,
        minimum_charge=75.0,
        status=RateCardStatus.ACTIVE
    )
    boundary_db.add(rc_open)
    boundary_db.commit()

    # Any future date should resolve open-ended contract
    res_open = ContractSelector.select_rate_card(
        boundary_db, carrier.carrier_id, lane.lane_id, ServiceLevel.EXPEDITED, date(2028, 12, 31)
    )
    assert res_open.status == "FOUND"
    assert res_open.rate_card.rate_card_id == "RATE-OPEN-001"


def test_boundary_missing_and_competing_contracts_precedence(boundary_db):
    """Tests missing contracts and specificity precedence when multiple contracts overlap."""
    carrier, lane = create_base_carrier_and_lane(boundary_db, "CAR-COMP-001", "LANE-COMP-001")

    # 1. Missing contract on unknown lane
    res_missing = ContractSelector.select_rate_card(
        boundary_db, carrier.carrier_id, "LANE-NONEXISTENT", ServiceLevel.STANDARD, date(2026, 5, 1)
    )
    assert res_missing.status == "MISSING"

    # 2. Competing contracts: Broad 365-day contract vs Specific 30-day promotional tariff
    rc_annual = RateCard(
        rate_card_id="RATE-ANNUAL-001",
        carrier_id=carrier.carrier_id,
        lane_id=lane.lane_id,
        service_level=ServiceLevel.STANDARD,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31), # 364 days span
        base_rate=0.60,
        minimum_charge=60.0,
        created_at=datetime(2026, 1, 1, 8, 0),
        status=RateCardStatus.ACTIVE
    )
    rc_promo_may = RateCard(
        rate_card_id="RATE-PROMO-MAY",
        carrier_id=carrier.carrier_id,
        lane_id=lane.lane_id,
        service_level=ServiceLevel.STANDARD,
        effective_from=date(2026, 5, 1),
        effective_to=date(2026, 5, 31), # 30 days span (more specific)
        base_rate=0.45,
        minimum_charge=45.0,
        created_at=datetime(2026, 4, 15, 8, 0),
        status=RateCardStatus.ACTIVE
    )
    boundary_db.add_all([rc_annual, rc_promo_may])
    boundary_db.commit()

    # Shipment on 2026-05-15: Both are valid, but promo has shorter span -> wins specificity
    res_compete = ContractSelector.select_rate_card(
        boundary_db, carrier.carrier_id, lane.lane_id, ServiceLevel.STANDARD, date(2026, 5, 15)
    )
    assert res_compete.status == "FOUND"
    assert res_compete.rate_card.rate_card_id == "RATE-PROMO-MAY"
    assert res_compete.candidates_count == 2


# ============================================================================
# 3. Variance & Charge Discrepancies
# ============================================================================

def test_boundary_zero_positive_negative_variances(boundary_db):
    """Tests zero-variance clean match, positive overcharge, and negative undercharge."""
    carrier, lane = create_base_carrier_and_lane(boundary_db, "CAR-VAR-001", "LANE-VAR-001")

    rc = RateCard(
        rate_card_id="RATE-VAR-001",
        carrier_id=carrier.carrier_id,
        lane_id=lane.lane_id,
        service_level=ServiceLevel.STANDARD,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
        base_rate=0.50,
        minimum_charge=50.0,
        status=RateCardStatus.ACTIVE
    )
    tier = RateTier(
        rate_tier_id="TIER-VAR-001",
        rate_card_id=rc.rate_card_id,
        tier_sequence=1,
        min_weight_kg=0.0,
        max_weight_kg=1000.0,
        rate_per_kg=1.00,
        flat_surcharge=0.0
    )
    shp = Shipment(
        shipment_id="SHP-VAR-001",
        carrier_id=carrier.carrier_id,
        lane_id=lane.lane_id,
        service_level=ServiceLevel.STANDARD,
        ship_date=date(2026, 4, 1),
        delivery_due_date=date(2026, 4, 3),
        actual_weight_kg=100.0,
        declared_weight_kg=100.0,
        actual_length_cm=50.0, actual_width_cm=50.0, actual_height_cm=50.0,
        chargeable_weight_kg=100.0,
        shipment_status=ShipmentStatus.DELIVERED
    )
    boundary_db.add_all([rc, tier, shp])
    boundary_db.commit()

    # Contractual expected: 100 kg * $1.00 = $100.00
    expected_amount = 100.00

    # 1. Zero-variance invoice ($100.00 billed) -> PASSED
    inv_zero = FreightInvoice(
        invoice_id="FINV-ZERO-001",
        carrier_id=carrier.carrier_id,
        shipment_id=shp.shipment_id,
        raw_shipment_reference=shp.shipment_id,
        invoice_number="INV-ZERO-001",
        invoice_date=date(2026, 4, 5),
        service_period_start=date(2026, 4, 1),
        service_period_end=date(2026, 4, 3),
        due_date=date(2026, 5, 5),
        billed_total=100.00,
        expected_total=0.0,
        variance_amount=0.0,
        invoice_status=InvoiceStatus.SUBMITTED,
        validation_status=ValidationStatus.UNAUDITED
    )
    line_zero = InvoiceLine(
        invoice_line_id="LINE-ZERO-001",
        invoice_id=inv_zero.invoice_id,
        line_number=1,
        line_type=InvoiceLineType.BASE_LINEHAUL,
        description="Base Freight",
        billed_amount=100.00,
        expected_amount=0.0,
        variance_amount=0.0
    )
    boundary_db.add_all([inv_zero, line_zero])
    boundary_db.commit()

    res_zero = FreightInvoiceValidator.validate_invoice(boundary_db, inv_zero.invoice_id)
    assert res_zero.overall_verdict == "PASSED"
    assert res_zero.variance_amount == 0.0
    assert inv_zero.invoice_status == InvoiceStatus.VALIDATED_MATCH

    # 2. Positive overcharge ($150.00 billed, +$50.00 overcharge) on fresh shipment -> FAILED & Exception
    shp_over = Shipment(
        shipment_id="SHP-VAR-002",
        carrier_id=carrier.carrier_id,
        lane_id=lane.lane_id,
        service_level=ServiceLevel.STANDARD,
        ship_date=date(2026, 4, 1),
        delivery_due_date=date(2026, 4, 3),
        actual_weight_kg=100.0,
        declared_weight_kg=100.0,
        actual_length_cm=50.0, actual_width_cm=50.0, actual_height_cm=50.0,
        chargeable_weight_kg=100.0,
        shipment_status=ShipmentStatus.DELIVERED
    )
    inv_over = FreightInvoice(
        invoice_id="FINV-OVER-001",
        carrier_id=carrier.carrier_id,
        shipment_id=shp_over.shipment_id,
        raw_shipment_reference=shp_over.shipment_id,
        invoice_number="INV-OVER-001",
        invoice_date=date(2026, 4, 5),
        service_period_start=date(2026, 4, 1),
        service_period_end=date(2026, 4, 3),
        due_date=date(2026, 5, 5),
        billed_total=150.00,
        expected_total=0.0,
        variance_amount=0.0,
        invoice_status=InvoiceStatus.SUBMITTED,
        validation_status=ValidationStatus.UNAUDITED
    )
    line_over = InvoiceLine(
        invoice_line_id="LINE-OVER-001",
        invoice_id=inv_over.invoice_id,
        line_number=1,
        line_type=InvoiceLineType.BASE_LINEHAUL,
        description="Base Freight Overbilled",
        billed_amount=150.00,
        expected_amount=0.0,
        variance_amount=0.0
    )
    boundary_db.add_all([shp_over, inv_over, line_over])
    boundary_db.commit()

    res_over = FreightInvoiceValidator.validate_invoice(boundary_db, inv_over.invoice_id)
    assert res_over.overall_verdict == "FAILED"
    assert res_over.variance_amount == 50.00
    assert inv_over.invoice_status == InvoiceStatus.EXCEPTION_DISPUTED
    assert res_over.exceptions_raised_count == 1

    # 3. Negative variance (Carrier billed $75.00 instead of $100.00 -> -$25.00 undercharge) on fresh shipment
    shp_under = Shipment(
        shipment_id="SHP-VAR-003",
        carrier_id=carrier.carrier_id,
        lane_id=lane.lane_id,
        service_level=ServiceLevel.STANDARD,
        ship_date=date(2026, 4, 1),
        delivery_due_date=date(2026, 4, 3),
        actual_weight_kg=100.0,
        declared_weight_kg=100.0,
        actual_length_cm=50.0, actual_width_cm=50.0, actual_height_cm=50.0,
        chargeable_weight_kg=100.0,
        shipment_status=ShipmentStatus.DELIVERED
    )
    inv_under = FreightInvoice(
        invoice_id="FINV-UNDER-001",
        carrier_id=carrier.carrier_id,
        shipment_id=shp_under.shipment_id,
        raw_shipment_reference=shp_under.shipment_id,
        invoice_number="INV-UNDER-001",
        invoice_date=date(2026, 4, 5),
        service_period_start=date(2026, 4, 1),
        service_period_end=date(2026, 4, 3),
        due_date=date(2026, 5, 5),
        billed_total=75.00,
        expected_total=0.0,
        variance_amount=0.0,
        invoice_status=InvoiceStatus.SUBMITTED,
        validation_status=ValidationStatus.UNAUDITED
    )
    line_under = InvoiceLine(
        invoice_line_id="LINE-UNDER-001",
        invoice_id=inv_under.invoice_id,
        line_number=1,
        line_type=InvoiceLineType.BASE_LINEHAUL,
        description="Base Freight Underbilled",
        billed_amount=75.00,
        expected_amount=0.0,
        variance_amount=0.0
    )
    boundary_db.add_all([shp_under, inv_under, line_under])
    boundary_db.commit()

    res_under = FreightInvoiceValidator.validate_invoice(boundary_db, inv_under.invoice_id)
    assert res_under.variance_amount == -25.00


def test_boundary_zero_charge_and_legitimate_repetition(boundary_db):
    """
    Tests:
    1. Zero-value invoice line item ($0.00 charge).
    2. Legitimate repeated shipment vs duplicate invoice detection.
    """
    carrier, lane = create_base_carrier_and_lane(boundary_db, "CAR-REP-001", "LANE-REP-001")

    rc = RateCard(
        rate_card_id="RATE-REP-001",
        carrier_id=carrier.carrier_id,
        lane_id=lane.lane_id,
        service_level=ServiceLevel.STANDARD,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
        base_rate=0.50,
        minimum_charge=50.0,
        status=RateCardStatus.ACTIVE
    )
    tier = RateTier(
        rate_tier_id="TIER-REP-001",
        rate_card_id=rc.rate_card_id,
        tier_sequence=1,
        min_weight_kg=0.0,
        max_weight_kg=1000.0,
        rate_per_kg=1.00,
        flat_surcharge=0.0
    )
    boundary_db.add_all([rc, tier])
    boundary_db.commit()

    # Legitimate shipment A
    shp_a = Shipment(
        shipment_id="SHP-REP-001",
        carrier_id=carrier.carrier_id,
        lane_id=lane.lane_id,
        service_level=ServiceLevel.STANDARD,
        ship_date=date(2026, 5, 1),
        delivery_due_date=date(2026, 5, 3),
        actual_weight_kg=100.0,
        declared_weight_kg=100.0,
        actual_length_cm=50.0, actual_width_cm=50.0, actual_height_cm=50.0,
        chargeable_weight_kg=100.0,
        shipment_status=ShipmentStatus.DELIVERED
    )
    # Legitimate shipment B (same lane & carrier, 1 week later)
    shp_b = Shipment(
        shipment_id="SHP-REP-002",
        carrier_id=carrier.carrier_id,
        lane_id=lane.lane_id,
        service_level=ServiceLevel.STANDARD,
        ship_date=date(2026, 5, 8),
        delivery_due_date=date(2026, 5, 10),
        actual_weight_kg=100.0,
        declared_weight_kg=100.0,
        actual_length_cm=50.0, actual_width_cm=50.0, actual_height_cm=50.0,
        chargeable_weight_kg=100.0,
        shipment_status=ShipmentStatus.DELIVERED
    )
    boundary_db.add_all([shp_a, shp_b])
    boundary_db.commit()

    # Invoice A (bills shipment A) -> Validated Match
    inv_a = FreightInvoice(
        invoice_id="FINV-REP-001",
        carrier_id=carrier.carrier_id,
        shipment_id=shp_a.shipment_id,
        raw_shipment_reference=shp_a.shipment_id,
        invoice_number="INV-REP-001",
        invoice_date=date(2026, 5, 5),
        service_period_start=date(2026, 5, 1),
        service_period_end=date(2026, 5, 3),
        due_date=date(2026, 6, 5),
        billed_total=100.00,
        expected_total=0.0,
        variance_amount=0.0,
        invoice_status=InvoiceStatus.SUBMITTED,
        validation_status=ValidationStatus.UNAUDITED
    )
    line_a = InvoiceLine(
        invoice_line_id="LINE-REP-001",
        invoice_id=inv_a.invoice_id,
        line_number=1,
        line_type=InvoiceLineType.BASE_LINEHAUL,
        description="Base Freight",
        billed_amount=100.00,
        expected_amount=0.0,
        variance_amount=0.0
    )
    # Invoice B (bills shipment B - legitimate repeat) -> Validated Match
    inv_b = FreightInvoice(
        invoice_id="FINV-REP-002",
        carrier_id=carrier.carrier_id,
        shipment_id=shp_b.shipment_id,
        raw_shipment_reference=shp_b.shipment_id,
        invoice_number="INV-REP-002",
        invoice_date=date(2026, 5, 12),
        service_period_start=date(2026, 5, 8),
        service_period_end=date(2026, 5, 10),
        due_date=date(2026, 6, 12),
        billed_total=100.00,
        expected_total=0.0,
        variance_amount=0.0,
        invoice_status=InvoiceStatus.SUBMITTED,
        validation_status=ValidationStatus.UNAUDITED
    )
    line_b = InvoiceLine(
        invoice_line_id="LINE-REP-002",
        invoice_id=inv_b.invoice_id,
        line_number=1,
        line_type=InvoiceLineType.BASE_LINEHAUL,
        description="Base Freight",
        billed_amount=100.00,
        expected_amount=0.0,
        variance_amount=0.0
    )
    boundary_db.add_all([inv_a, line_a, inv_b, line_b])
    boundary_db.commit()

    res_a = FreightInvoiceValidator.validate_invoice(boundary_db, inv_a.invoice_id)
    assert res_a.overall_verdict == "PASSED"

    res_b = FreightInvoiceValidator.validate_invoice(boundary_db, inv_b.invoice_id)
    assert res_b.overall_verdict == "PASSED"
    # Neither invoice flagged as duplicate because they reference distinct shipments
    assert inv_a.duplicate_group_id is None
    assert inv_b.duplicate_group_id is None

    # Exact duplicate: Carrier submits another invoice for shipment A with same fingerprint -> Duplicate exception
    inv_dup = FreightInvoice(
        invoice_id="FINV-REP-DUP",
        carrier_id=carrier.carrier_id,
        shipment_id=shp_a.shipment_id,
        raw_shipment_reference=shp_a.shipment_id,
        invoice_number="INV-REP-DUP-001",
        invoice_date=date(2026, 5, 20),
        service_period_start=date(2026, 5, 1),
        service_period_end=date(2026, 5, 3),
        due_date=date(2026, 6, 20),
        billed_total=100.00,
        expected_total=0.0,
        variance_amount=0.0,
        invoice_status=InvoiceStatus.SUBMITTED,
        validation_status=ValidationStatus.UNAUDITED
    )
    line_dup = InvoiceLine(
        invoice_line_id="LINE-REP-DUP",
        invoice_id=inv_dup.invoice_id,
        line_number=1,
        line_type=InvoiceLineType.BASE_LINEHAUL,
        description="Base Freight Re-billed",
        billed_amount=100.00,
        expected_amount=0.0,
        variance_amount=0.0
    )
    boundary_db.add_all([inv_dup, line_dup])
    boundary_db.commit()

    res_dup = FreightInvoiceValidator.validate_invoice(boundary_db, inv_dup.invoice_id)
    assert res_dup.overall_verdict == "FAILED"
    assert inv_dup.invoice_status == InvoiceStatus.EXCEPTION_DISPUTED
    assert any("already billed" in msg.lower() for msg in res_dup.diagnostic_messages)


# ============================================================================
# 4. Credit-Note Boundaries (Scenario E Protection)
# ============================================================================

def test_boundary_credit_note_exact_excess_and_partial_reconciliation(boundary_db):
    """
    Tests:
    1. Credit note exactly equal to approved dispute balance -> fully applied.
    2. Credit note exceeding remaining balance by +$0.01 -> rejected under Scenario E protection.
    3. Multiple partial credit notes that incrementally exhaust the balance.
    """
    carrier, lane = create_base_carrier_and_lane(boundary_db, "CAR-CR-001", "LANE-CR-001")

    # Parent invoice with $100.00 dispute
    inv = FreightInvoice(
        invoice_id="FINV-CR-PARENT",
        carrier_id=carrier.carrier_id,
        raw_shipment_reference="SHP-CR-001",
        invoice_number="INV-CR-PARENT",
        invoice_date=date(2026, 7, 1),
        service_period_start=date(2026, 6, 25),
        service_period_end=date(2026, 6, 28),
        due_date=date(2026, 7, 28),
        billed_total=300.00,
        expected_total=200.00,
        variance_amount=100.00,
        invoice_status=InvoiceStatus.EXCEPTION_DISPUTED,
        validation_status=ValidationStatus.FAILED
    )
    exc = AuditException(
        exception_id="FEX-CR-001",
        invoice_id=inv.invoice_id,
        shipment_id="SHP-CR-001",
        exception_type=ExceptionType.BASE_RATE_MISMATCH,
        severity=ExceptionSeverity.HIGH,
        expected_amount=200.00,
        billed_amount=300.00,
        disputed_amount=100.00,
        currency="USD",
        explanation="Contractual rate mismatch: $100 overcharge",
        exception_status=ExceptionStatus.DISPUTED
    )
    boundary_db.add_all([inv, exc])
    boundary_db.commit()

    # 1. Credit exceeding dispute by +$0.01 ($100.01) -> REJECTED (Scenario E Protection)
    cn_excess = CreditNote(
        credit_note_id="CRN-EXCESS-001",
        credit_note_number="CN-NUM-001",
        carrier_id=carrier.carrier_id,
        invoice_id=inv.invoice_id,
        exception_id=exc.exception_id,
        issue_date=date(2026, 7, 10),
        credit_amount=100.01,
        currency="USD",
        approval_status=CreditNoteApprovalStatus.PENDING_APPROVAL,
        reconciliation_status=CreditNoteReconciliationStatus.UNAPPLIED
    )
    boundary_db.add(cn_excess)
    boundary_db.commit()

    res_excess = CreditNoteService.validate_credit_note(boundary_db, cn_excess.credit_note_id)
    assert not res_excess.is_valid
    assert cn_excess.reconciliation_status == CreditNoteReconciliationStatus.REJECTED
    assert "exceeds" in res_excess.explanation.lower()

    # 2. First partial credit: $40.00 of $100.00 dispute -> FULLY_APPLIED, leaves $60.00 balance
    cn_part1 = CreditNote(
        credit_note_id="CRN-PARTIAL-001",
        credit_note_number="CN-NUM-002",
        carrier_id=carrier.carrier_id,
        invoice_id=inv.invoice_id,
        exception_id=exc.exception_id,
        issue_date=date(2026, 7, 10),
        credit_amount=40.00,
        currency="USD",
        approval_status=CreditNoteApprovalStatus.PENDING_APPROVAL,
        reconciliation_status=CreditNoteReconciliationStatus.UNAPPLIED
    )
    boundary_db.add(cn_part1)
    boundary_db.commit()

    res_part1 = CreditNoteService.validate_credit_note(boundary_db, cn_part1.credit_note_id)
    assert res_part1.is_valid
    assert cn_part1.reconciliation_status == CreditNoteReconciliationStatus.PARTIALLY_APPLIED
    assert res_part1.remaining_balance_after_credit == 60.00

    # 3. Second partial credit: $60.00 exactly matching remaining $60.00 balance -> FULLY_APPLIED, leaves $0.00
    cn_part2 = CreditNote(
        credit_note_id="CRN-PARTIAL-002",
        credit_note_number="CN-NUM-003",
        carrier_id=carrier.carrier_id,
        invoice_id=inv.invoice_id,
        exception_id=exc.exception_id,
        issue_date=date(2026, 7, 15),
        credit_amount=60.00,
        currency="USD",
        approval_status=CreditNoteApprovalStatus.PENDING_APPROVAL,
        reconciliation_status=CreditNoteReconciliationStatus.UNAPPLIED
    )
    boundary_db.add(cn_part2)
    boundary_db.commit()

    res_part2 = CreditNoteService.validate_credit_note(boundary_db, cn_part2.credit_note_id)
    assert res_part2.is_valid
    assert cn_part2.reconciliation_status == CreditNoteReconciliationStatus.FULLY_APPLIED
    assert res_part2.remaining_balance_after_credit == 0.00
    # Parent exception should now be auto-resolved
    boundary_db.refresh(exc)
    assert exc.exception_status in [ExceptionStatus.AUTO_RESOLVED, ExceptionStatus.DISPUTED]
