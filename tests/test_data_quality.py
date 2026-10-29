"""
Test Suite for Data-Quality Validation, Exports, and Reproducibility (Phase 5).
Tests primary key integrity, foreign key references, allowed enums, chronological dates,
arithmetic reconciliation, duplicate prevention, and bit-for-bit reproducibility.
"""

import pytest
import os
import json
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.database import Base
from backend.app.generator.generator import SyntheticDataGenerator
from backend.app.generator.data_quality import DataQualityValidator
from backend.app.generator.reproducibility import ReproducibilityVerifier
from backend.app.generator.exporter import DataExporter


@pytest.fixture(scope="module")
def seeded_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    generator = SyntheticDataGenerator(profile_name="test", seed=20261022)
    generator.generate_all(db)
    yield db
    db.close()


def test_primary_keys_integrity(seeded_db):
    validator = DataQualityValidator(seeded_db)
    res = validator.check_primary_keys()
    assert res["status"] == "PASSED"
    assert res["null_pks"] == 0
    assert res["duplicate_pks"] == 0
    assert res["pattern_mismatches"] == 0
    assert res["records_checked"] > 0


def test_foreign_keys_and_intentional_anomalies(seeded_db):
    validator = DataQualityValidator(seeded_db)
    res = validator.check_foreign_keys()
    assert res["status"] == "PASSED"
    assert res["unintentional_dangling_references"] == 0
    # Intentional Scenario A (unmatched shipment reference) must be tracked
    assert res["intentional_unmatched_references"] > 0


def test_allowed_values_and_enums(seeded_db):
    validator = DataQualityValidator(seeded_db)
    res = validator.check_allowed_values()
    assert res["status"] == "PASSED"
    assert res["invalid_enums_count"] == 0


def test_chronological_dates_integrity(seeded_db):
    validator = DataQualityValidator(seeded_db)
    res = validator.check_dates()
    assert res["status"] == "PASSED"
    assert res["chronological_date_errors"] == 0


def test_arithmetic_reconciliation(seeded_db):
    validator = DataQualityValidator(seeded_db)
    res = validator.check_arithmetic()
    assert res["status"] == "PASSED"
    assert res["arithmetic_defects_count"] == 0


def test_duplicate_checks(seeded_db):
    validator = DataQualityValidator(seeded_db)
    res = validator.check_duplicates()
    assert res["status"] == "PASSED"
    assert res["duplicate_invoice_number_violations"] == 0


def test_lifecycle_state_machine_integrity(seeded_db):
    validator = DataQualityValidator(seeded_db)
    res = validator.check_lifecycle()
    assert res["status"] == "PASSED"
    assert res["lifecycle_defects_count"] == 0


def test_ground_truth_coverage(seeded_db):
    validator = DataQualityValidator(seeded_db)
    res = validator.check_ground_truth_coverage()
    assert res["status"] == "PASSED"
    assert res["total_ground_truth_labels"] > 0
    assert res["anomalies_labelled"] > 0
    assert res["clean_invoices_labelled"] > 0


def test_data_quality_report_export(seeded_db, tmp_path):
    validator = DataQualityValidator(seeded_db)
    paths = validator.export_reports(output_dir=str(tmp_path))

    assert os.path.exists(paths["json_summary"])
    assert os.path.exists(paths["markdown_summary"])

    with open(paths["json_summary"], "r", encoding="utf-8") as f:
        summary_data = json.load(f)

    assert summary_data["dataset_status"] == "PASSED"
    assert summary_data["unintentional_defects_count"] == 0
    assert summary_data["intentional_anomalies_count"] > 0


def test_dual_run_bit_for_bit_reproducibility():
    res = ReproducibilityVerifier.verify(profile_name="test", seed=20261022)
    assert res["reproducible"] is True
    assert res["mismatches_count"] == 0
    assert res["files_compared"] > 0
    assert res["entities_compared"] > 0
