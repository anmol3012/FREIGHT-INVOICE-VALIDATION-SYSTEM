"""
Tests for Ground Truth Leakage and Architectural Isolation (Phase 4).
Ensures that the operational validation engine operates completely blind to
ground-truth labels and evaluation datasets.
"""

import ast
import os
import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.core.database import Base
from backend.app.models.carrier import Carrier
from backend.app.models.lane import Lane
from backend.app.models.rate_card import RateCard, RateTier
from backend.app.models.shipment import Shipment, ShipmentLeg
from backend.app.models.invoice import FreightInvoice, InvoiceLine
from backend.app.models.ground_truth import GroundTruthLabel
from backend.app.models.enums import (
    CarrierStatus, LaneStatus, RateCardStatus, ServiceLevel,
    ShipmentStatus, ShipmentLegStatus, InvoiceStatus, ValidationStatus,
    InvoiceLineType
)
from backend.app.engine.validator import InvoiceValidator


def test_ast_engine_modules_never_import_ground_truth():
    """
    AST inspection verifying that no operational engine module in backend/app/engine/
    imports GroundTruthLabel or references ground_truth_labels.
    (Only evaluator.py in the offline evaluation suite is permitted to join ground truth).
    """
    engine_dir = os.path.join(os.path.dirname(__file__), "..", "backend", "app", "engine")
    engine_files = [
        f for f in os.listdir(engine_dir)
        if f.endswith(".py") and f != "evaluator.py" # evaluator is the offline evaluation service
    ]

    forbidden_identifiers = {"GroundTruthLabel", "ground_truth_labels", "AnomalyScenarioType"}

    for filename in engine_files:
        filepath = os.path.join(engine_dir, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=filename)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name not in forbidden_identifiers, (
                        f"Leakage detected in {filename}: imports {alias.name}"
                    )
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    assert alias.name not in forbidden_identifiers, (
                        f"Leakage detected in {filename}: imports {alias.name} from {node.module}"
                    )
            elif isinstance(node, ast.Name):
                assert node.id not in {"GroundTruthLabel"}, (
                    f"Leakage detected in {filename}: references GroundTruthLabel"
                )


def test_validation_engine_output_identical_with_or_without_ground_truth():
    """
    Functional test verifying that the validation engine produces exactly the same
    validation status, calculated expected amount, and exceptions whether
    ground truth records exist or not in the database.
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        # 1. Seed base master data
        carrier = Carrier(
            carrier_id="CAR-000001",
            carrier_code="CAR000001",
            carrier_name="Alpha Freight Lines",
            status=CarrierStatus.ACTIVE,
            country_code="USA"
        )
        lane = Lane(
            lane_id="LANE-000001",
            origin_location_code="ORD",
            destination_location_code="DFW",
            origin_city="Chicago",
            destination_city="Dallas",
            origin_country="USA",
            destination_country="USA",
            distance_km=1480.0,
            status=LaneStatus.ACTIVE
        )
        rate_card = RateCard(
            rate_card_id="RATE-CAR-000001-2026-01",
            carrier_id=carrier.carrier_id,
            lane_id=lane.lane_id,
            service_level=ServiceLevel.STANDARD,
            effective_from=date(2026, 1, 1),
            effective_to=date(2026, 12, 31),
            base_rate=2.50,
            minimum_charge=100.0,
            dimensional_weight_divisor=5000.0,
            currency="USD",
            status=RateCardStatus.ACTIVE
        )
        shipment = Shipment(
            shipment_id="SHP-2026-000001",
            carrier_id=carrier.carrier_id,
            lane_id=lane.lane_id,
            service_level=ServiceLevel.STANDARD,
            ship_date=date(2026, 3, 1),
            delivery_due_date=date(2026, 3, 3),
            actual_length_cm=100.0,
            actual_width_cm=100.0,
            actual_height_cm=100.0,
            actual_weight_kg=200.0,
            declared_weight_kg=200.0,
            chargeable_weight_kg=200.0,
            currency="USD",
            shipment_status=ShipmentStatus.DELIVERED
        )
        invoice = FreightInvoice(
            invoice_id="FINV-2026-000001",
            carrier_id=carrier.carrier_id,
            shipment_id=shipment.shipment_id,
            raw_shipment_reference="SHP-2026-000001",
            invoice_number="INV-2026-000001",
            invoice_date=date(2026, 3, 5),
            service_period_start=date(2026, 3, 1),
            service_period_end=date(2026, 3, 3),
            due_date=date(2026, 4, 4),
            currency="USD",
            billed_total=700.00,
            expected_total=0.0,
            variance_amount=0.0,
            invoice_status=InvoiceStatus.SUBMITTED,
            validation_status=ValidationStatus.UNAUDITED
        )
        line = InvoiceLine(
            invoice_line_id="FLINE-FINV-2026-000001-01",
            invoice_id=invoice.invoice_id,
            line_number=1,
            line_type=InvoiceLineType.BASE_LINEHAUL,
            description="Base Freight Charge",
            quantity=200.0,
            unit_of_measure="KG",
            unit_rate=3.50,
            billed_amount=700.00,
            expected_amount=0.0,
            variance_amount=0.0
        )

        db.add_all([carrier, lane, rate_card, shipment, invoice, line])
        db.flush()

        # Step 2: Validate invoice when Ground Truth is completely empty
        assert db.query(GroundTruthLabel).count() == 0
        run1 = InvoiceValidator.validate_invoice(db, invoice.invoice_id)

        status_without_gt = run1.validation_status
        expected_without_gt = run1.expected_total
        variance_without_gt = run1.variance_amount
        exceptions_without_gt = run1.exceptions_raised_count

        # Step 3: Insert Ground Truth anomaly label
        gt_label = GroundTruthLabel(
            label_id="GTL-2026-000001",
            invoice_id=invoice.invoice_id,
            invoice_number=invoice.invoice_number,
            raw_shipment_reference=invoice.raw_shipment_reference,
            carrier_id=carrier.carrier_id,
            carrier_code=carrier.carrier_code,
            issue_type="SCENARIO_B_EXPIRED_CONTRACT",
            is_anomaly=True,
            expected_decision="FAIL",
            ground_truth_billed=700.00,
            ground_truth_expected=500.00,
            injected_variance=200.00
        )
        db.add(gt_label)
        db.flush()
        assert db.query(GroundTruthLabel).count() == 1

        # Reset invoice validation fields to re-run
        invoice.validation_status = ValidationStatus.UNAUDITED
        invoice.expected_total = 0.0
        invoice.variance_amount = 0.0

        # Step 4: Validate again with Ground Truth present in the database
        run2 = InvoiceValidator.validate_invoice(db, invoice.invoice_id)

        # Step 5: Verify identical results
        assert run2.validation_status == status_without_gt
        assert run2.expected_total == expected_without_gt
        assert run2.variance_amount == variance_without_gt
        assert run2.exceptions_raised_count == exceptions_without_gt

    finally:
        db.close()
