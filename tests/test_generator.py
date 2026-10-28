import os
import shutil
import pytest
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.core.database import Base
from backend.app.generator.generator import DeterministicDataGenerator
from backend.app.generator.exporter import DataExporter
from backend.app.generator.config import PROFILES
from backend.app.engine.calculator import ContractualFreightCalculator
from backend.app.models.carrier import Carrier
from backend.app.models.lane import Lane
from backend.app.models.rate_card import RateCard, RateTier
from backend.app.models.shipment import Shipment, ShipmentLeg, WeightMeasurement, DeliveryEvidence
from backend.app.models.invoice import FreightInvoice, InvoiceLine
from backend.app.models.audit_exception import AuditException
from backend.app.models.credit_note import CreditNote
from backend.app.models.ground_truth import GroundTruthLabel
from backend.app.models.enums import CreditNoteApprovalStatus


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()
    yield db
    db.close()


def test_generator_test_profile_volumes(test_db):
    """Verifies that the test profile produces the expected record counts."""
    gen = DeterministicDataGenerator(profile_name="test", seed=20261022)
    counts = gen.generate_all(test_db)

    profile = PROFILES["test"]
    assert counts["carriers"] == profile.num_carriers
    assert counts["lanes"] == profile.num_lanes
    assert counts["accessorials"] == profile.num_accessorials
    assert counts["shipments"] == profile.num_shipments
    assert counts["freight_invoices"] == profile.num_invoices
    assert counts["ground_truth_labels"] == profile.num_invoices
    assert counts["invoice_lines"] > counts["freight_invoices"]


def test_freight_weight_formulas():
    """Validates contractual weight and dimensional weight formulas."""
    l, w, h = 120.0, 80.0, 100.0
    divisor = 5000.0

    # Dim weight: (120 * 80 * 100) / 5000 = 960,000 / 5000 = 192.0 kg
    dim_wt = ContractualFreightCalculator.calculate_dimensional_weight(l, w, h, divisor)
    assert dim_wt == 192.0

    # Chargeable weight with actual 150 kg (dim weight 192 > 150) -> 192 kg
    chg_wt = ContractualFreightCalculator.calculate_chargeable_weight(150.0, l, w, h, divisor, rounding_policy="CEIL_KG")
    assert chg_wt == 192.0

    # Chargeable weight with actual 250.4 kg (actual 250.4 > 192) -> ceil(250.4) = 251.0 kg
    chg_wt_actual = ContractualFreightCalculator.calculate_chargeable_weight(250.4, l, w, h, divisor, rounding_policy="CEIL_KG")
    assert chg_wt_actual == 251.0


def test_dependency_referential_integrity(test_db):
    """Validates that all child records have valid foreign key references."""
    gen = DeterministicDataGenerator(profile_name="test", seed=20261022)
    gen.generate_all(test_db)

    # 1. Rate cards refer to valid carriers and lanes
    carrier_ids = {c.carrier_id for c in test_db.query(Carrier.carrier_id).all()}
    lane_ids = {l.lane_id for l in test_db.query(Lane.lane_id).all()}

    rate_cards = test_db.query(RateCard).all()
    for rc in rate_cards:
        assert rc.carrier_id in carrier_ids
        assert rc.lane_id in lane_ids

    # 2. Shipments refer to valid carriers and lanes
    shipments = test_db.query(Shipment).all()
    shipment_ids = {s.shipment_id for s in shipments}
    for s in shipments:
        assert s.carrier_id in carrier_ids
        assert s.lane_id in lane_ids

    # 3. Invoices refer to valid carriers, and valid shipments unless intentional untrusted ref
    invoices = test_db.query(FreightInvoice).all()
    for inv in invoices:
        assert inv.carrier_id in carrier_ids
        if inv.shipment_id is not None:
            assert inv.shipment_id in shipment_ids
        else:
            # Must be intentionally untrusted staging reference with a rejection reason
            assert inv.reference_rejection_reason is not None
            assert inv.raw_shipment_reference.startswith("SHP-UNKNOWN-")


def test_mandatory_anomaly_scenarios(test_db):
    """Verifies that all required anomaly types are injected and logged in ground truth."""
    gen = DeterministicDataGenerator(profile_name="test", seed=20261022)
    gen.generate_all(test_db)

    gt_labels = test_db.query(GroundTruthLabel).all()
    issues_found = {gt.issue_type for gt in gt_labels}

    # Verify presence of all primary test scenarios
    assert "NORMAL" in issues_found
    assert "UNKNOWN_SHIPMENT_REF" in issues_found
    assert "EXPIRED_RATE_CARD" in issues_found
    assert "INCORRECT_WEIGHT_TIER" in issues_found
    assert "DUPLICATE_FUEL_SURCHARGE" in issues_found
    assert "EXCESSIVE_CREDIT_NOTE" in issues_found

    # Verify Scenario A (Untrusted staging ref with shipment_id = NULL)
    unknown_invs = test_db.query(FreightInvoice).filter(FreightInvoice.shipment_id == None).all()
    assert len(unknown_invs) >= 1
    for inv in unknown_invs:
        assert inv.reference_rejection_reason is not None

    # Verify Scenario E (Credit note exceeding approved dispute is rejected)
    excessive_cns = test_db.query(CreditNote).filter(
        CreditNote.approval_status == CreditNoteApprovalStatus.REJECTED
    ).all()
    assert len(excessive_cns) >= 1


def test_export_determinism(tmp_path):
    """
    Validates that two independent generator and export runs with the same seed
    produce 100% bit-for-bit identical files with matching SHA-256 checksums.
    """
    export_dir1 = tmp_path / "run1"
    export_dir2 = tmp_path / "run2"

    # --- Run 1 ---
    engine1 = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine1)
    db1 = sessionmaker(bind=engine1)()
    gen1 = DeterministicDataGenerator(profile_name="test", seed=20261022)
    gen1.generate_all(db1)

    exp1 = DataExporter(output_dir=str(export_dir1))
    res1 = exp1.export_all(db1, seed=20261022)
    db1.close()

    # --- Run 2 ---
    engine2 = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine2)
    db2 = sessionmaker(bind=engine2)()
    gen2 = DeterministicDataGenerator(profile_name="test", seed=20261022)
    gen2.generate_all(db2)

    exp2 = DataExporter(output_dir=str(export_dir2))
    res2 = exp2.export_all(db2, seed=20261022)
    db2.close()

    # Verify that every exported file has identical SHA-256 checksums between Run 1 and Run 2
    assert set(res1["file_checksums"].keys()) == set(res2["file_checksums"].keys())

    for filename, hash1 in res1["file_checksums"].items():
        hash2 = res2["file_checksums"][filename]
        assert hash1 == hash2, f"Checksum mismatch for {filename}: {hash1} != {hash2}"

    # Also verify checksums.sha256 manifests match
    manifest1 = (export_dir1 / "checksums.sha256").read_text(encoding="utf-8")
    manifest2 = (export_dir2 / "checksums.sha256").read_text(encoding="utf-8")
    assert manifest1 == manifest2
