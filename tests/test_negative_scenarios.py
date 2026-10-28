import pytest
from datetime import date, datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.core.database import Base
from backend.app.models.carrier import Carrier
from backend.app.models.rate_card import RateCard, RateLane, AccessorialRule
from backend.app.models.shipment import Shipment, WeightMeasurement, DeliveryRecord
from backend.app.models.invoice import InvoiceHeader, InvoiceLine
from backend.app.models.credit_note import CreditNote
from backend.app.engine.validator import InvoiceValidator

@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        # Seed test carrier, contract, shipment
        c = Carrier(carrier_code="TEST", name="Test Logistics", tax_id="12-3456789", payment_terms_days=30)
        db.add(c)
        db.flush()

        rc = RateCard(
            rate_card_code="RC-TEST", carrier_id=c.id, effective_date=date(2026, 1, 1),
            expiration_date=date(2026, 12, 31), base_rate_model="PER_CWT", minimum_charge_floor=80.0,
            fuel_base_price=3.00, fuel_surcharge_pct_per_interval=0.005, status="ACTIVE"
        )
        db.add(rc)
        db.flush()

        lane = RateLane(
            rate_card_id=rc.id, origin_zip_prefix="ALL", dest_zip_prefix="ALL",
            base_rate_cwt=10.00, minimum_charge=80.0
        )
        db.add(lane)

        ar = AccessorialRule(carrier_id=c.id, code="LIFTGATE", name="Liftgate", unit_rate=75.0, proof_required=True)
        ar2 = AccessorialRule(carrier_id=c.id, code="DETENTION", name="Detention", unit_rate=60.0, free_time_minutes=120)
        db.add_all([ar, ar2])

        s = Shipment(
            bol_number="BOL-SCENARIO-1", carrier_id=c.id, origin_zip="30301", origin_city="Atlanta", origin_state="GA",
            destination_zip="60601", destination_city="Chicago", destination_state="IL",
            pickup_date=date(2026, 4, 1), delivery_date=date(2026, 4, 3), current_fuel_index=3.00, dock_type="STANDARD_DOCK"
        )
        db.add(s)
        db.flush()

        wm = WeightMeasurement(
            shipment_id=s.id, gross_weight_lbs=2000.0, length_in=48.0, width_in=40.0, height_in=48.0,
            billable_weight_lbs=2000.0, certified=True # 20 CWT
        )
        dr = DeliveryRecord(
            shipment_id=s.id, delivered_at=datetime(2026, 4, 3, 14, 0), recipient_name="Dock Lead",
            facility_dock_type="STANDARD_DOCK", liftgate_actually_used=False, detention_minutes_recorded=60
        )
        db.add_all([wm, dr])
        db.commit()

        yield db
    finally:
        db.close()

def test_scenario_1_base_rate_mismatch(test_db):
    """Scenario 1: Carrier bills $15.00/CWT instead of contracted $10.00/CWT."""
    c = test_db.query(Carrier).first()
    s = test_db.query(Shipment).first()

    # Expected: 20 CWT * $10 = $200.00
    # Billed: 20 CWT * $15 = $300.00
    inv = InvoiceHeader(
        invoice_number="INV-SCEN-1", carrier_id=c.id, shipment_id=s.id, bol_number_billed=s.bol_number,
        invoice_date=date(2026, 4, 5), due_date=date(2026, 5, 5), total_billed_amount=300.00,
        status="PENDING_AUDIT"
    )
    test_db.add(inv)
    test_db.flush()

    line = InvoiceLine(
        invoice_id=inv.id, line_number=1, charge_type="LINEHAUL", charge_code="LH",
        description="Linehaul Base", billed_units=20.0, billed_rate=15.00, billed_amount=300.00
    )
    test_db.add(line)
    test_db.commit()

    val_inv = InvoiceValidator.validate_invoice(test_db, inv.id)
    assert val_inv.validation_status == "FAILED"
    assert val_inv.status == "EXCEPTION_DISPUTED"
    assert len(val_inv.exceptions) == 1
    assert val_inv.exceptions[0].category == "BASE_RATE_MISMATCH"
    assert val_inv.exceptions[0].variance_amount == 100.00

def test_scenario_2_weight_discrepancy(test_db):
    """Scenario 2: Carrier bills 35 CWT (3,500 lbs) instead of certified 20 CWT (2,000 lbs)."""
    c = test_db.query(Carrier).first()
    s = test_db.query(Shipment).first()

    inv = InvoiceHeader(
        invoice_number="INV-SCEN-2", carrier_id=c.id, shipment_id=s.id, bol_number_billed=s.bol_number,
        invoice_date=date(2026, 4, 5), due_date=date(2026, 5, 5), total_billed_amount=350.00,
        status="PENDING_AUDIT"
    )
    test_db.add(inv)
    test_db.flush()

    line = InvoiceLine(
        invoice_id=inv.id, line_number=1, charge_type="LINEHAUL", charge_code="LH",
        description="Linehaul Base", billed_units=35.0, billed_rate=10.00, billed_amount=350.00
    )
    test_db.add(line)
    test_db.commit()

    val_inv = InvoiceValidator.validate_invoice(test_db, inv.id)
    assert val_inv.validation_status == "FAILED"
    assert len(val_inv.exceptions) == 1
    assert val_inv.exceptions[0].category == "WEIGHT_DISCREPANCY"
    assert val_inv.exceptions[0].variance_amount == 150.00

def test_scenario_3_unauthorized_accessorial(test_db):
    """Scenario 3: Carrier bills $75.00 liftgate, but delivery record shows dock delivery with no liftgate."""
    c = test_db.query(Carrier).first()
    s = test_db.query(Shipment).first()

    inv = InvoiceHeader(
        invoice_number="INV-SCEN-3", carrier_id=c.id, shipment_id=s.id, bol_number_billed=s.bol_number,
        invoice_date=date(2026, 4, 5), due_date=date(2026, 5, 5), total_billed_amount=275.00,
        status="PENDING_AUDIT"
    )
    test_db.add(inv)
    test_db.flush()

    l1 = InvoiceLine(
        invoice_id=inv.id, line_number=1, charge_type="LINEHAUL", charge_code="LH",
        description="Linehaul Base", billed_units=20.0, billed_rate=10.00, billed_amount=200.00
    )
    l2 = InvoiceLine(
        invoice_id=inv.id, line_number=2, charge_type="ACCESSORIAL", charge_code="LIFTGATE",
        description="Liftgate Fee", billed_units=1.0, billed_rate=75.00, billed_amount=75.00
    )
    test_db.add_all([l1, l2])
    test_db.commit()

    val_inv = InvoiceValidator.validate_invoice(test_db, inv.id)
    assert val_inv.validation_status == "FAILED"
    unauth_exc = [e for e in val_inv.exceptions if e.category == "UNAUTHORIZED_ACCESSORIAL"]
    assert len(unauth_exc) == 1
    assert unauth_exc[0].variance_amount == 75.00

def test_scenario_4_duplicate_billing(test_db):
    """Scenario 4: Carrier submits a second invoice with identical carrier, BOL, and charges."""
    c = test_db.query(Carrier).first()
    s = test_db.query(Shipment).first()

    # Original invoice
    inv1 = InvoiceHeader(
        invoice_number="INV-ORIGINAL", carrier_id=c.id, shipment_id=s.id, bol_number_billed=s.bol_number,
        invoice_date=date(2026, 4, 5), due_date=date(2026, 5, 5), total_billed_amount=200.00,
        fingerprint_hash=InvoiceValidator.compute_invoice_fingerprint(c.id, s.bol_number, 200.00),
        status="PENDING_AUDIT"
    )
    test_db.add(inv1)
    test_db.flush()
    InvoiceValidator.validate_invoice(test_db, inv1.id)
    assert inv1.validation_status == "PASSED"

    # Duplicate invoice arrives later
    inv2 = InvoiceHeader(
        invoice_number="INV-DUPLICATE", carrier_id=c.id, shipment_id=s.id, bol_number_billed=s.bol_number,
        invoice_date=date(2026, 4, 10), due_date=date(2026, 5, 10), total_billed_amount=200.00,
        fingerprint_hash=InvoiceValidator.compute_invoice_fingerprint(c.id, s.bol_number, 200.00),
        status="PENDING_AUDIT"
    )
    test_db.add(inv2)
    test_db.flush()

    val_inv2 = InvoiceValidator.validate_invoice(test_db, inv2.id)
    assert val_inv2.is_duplicate is True
    assert val_inv2.duplicate_of_invoice_id == inv1.id
    assert val_inv2.validation_status == "FAILED"
    assert val_inv2.exceptions[0].category == "DUPLICATE_BILLING"

def test_scenario_5_credit_note_validation(test_db):
    """Scenario 5: Credit note reconciliation and over-credit protection."""
    c = test_db.query(Carrier).first()
    s = test_db.query(Shipment).first()

    # Invoice with $100 overbilling
    inv = InvoiceHeader(
        invoice_number="INV-DISPUTED", carrier_id=c.id, shipment_id=s.id, bol_number_billed=s.bol_number,
        invoice_date=date(2026, 4, 5), due_date=date(2026, 5, 5), total_billed_amount=300.00,
        calculated_expected_amount=200.00, total_variance_amount=100.00, status="EXCEPTION_DISPUTED"
    )
    test_db.add(inv)
    test_db.flush()

    # 1. Invalid excessive credit note for $500.00
    bad_cn = CreditNote(
        credit_note_number="CN-BAD-500", carrier_id=c.id, original_invoice_id=inv.id,
        issue_date=date(2026, 4, 20), credit_amount=500.00, remaining_balance=500.00, status="UNAPPLIED",
        reason_code="EXCESSIVE"
    )
    test_db.add(bad_cn)
    test_db.flush()

    res_bad = InvoiceValidator.validate_credit_note(test_db, bad_cn.id)
    assert res_bad.status == "REJECTED"
    assert "exceeds" in res_bad.rejection_reason

    # 2. Legitimate credit note for exact $100.00
    good_cn = CreditNote(
        credit_note_number="CN-GOOD-100", carrier_id=c.id, original_invoice_id=inv.id,
        issue_date=date(2026, 4, 20), credit_amount=100.00, remaining_balance=100.00, status="UNAPPLIED",
        reason_code="RATE_CORRECTION"
    )
    test_db.add(good_cn)
    test_db.flush()

    res_good = InvoiceValidator.validate_credit_note(test_db, good_cn.id)
    assert res_good.status == "FULLY_APPLIED"
    assert res_good.remaining_balance == 0.0
    assert inv.status == "EXCEPTION_APPROVED"
