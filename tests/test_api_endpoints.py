"""
Test Suite for FastAPI REST API Endpoints (Phase 5).
Tests dashboard KPIs, invoice listing, detail retrieval, on-demand validation,
historical traceability lineage, exception workflow transitions, manual overrides,
credit note validation, audit events, and offline accuracy evaluation.
"""

import pytest
from datetime import date, datetime
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from sqlalchemy.pool import StaticPool
from backend.app.core.database import Base, get_db
from backend.app.main import app
from backend.app.generator.generator import SyntheticDataGenerator
from backend.app.engine.validator import InvoiceValidator


@pytest.fixture(scope="module")
def api_test_client():
    """Sets up an in-memory SQLite database seeded with starter generator profile."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    seed_db = TestingSessionLocal()

    # Generate test dataset
    generator = SyntheticDataGenerator(profile_name="test", seed=20261022)
    generator.generate_all(seed_db)

    # Validate all invoices
    from backend.app.models.invoice import FreightInvoice
    for inv in seed_db.query(FreightInvoice).all():
        InvoiceValidator.validate_invoice(seed_db, inv.invoice_id)

    seed_db.commit()
    seed_db.close()

    # Dependency override
    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    yield client, TestingSessionLocal

    app.dependency_overrides.clear()


def test_api_dashboard_kpis(api_test_client):
    client, db = api_test_client
    resp = client.get("/api/v1/dashboard/kpis")
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_invoices"] == 25
    assert data["total_billed_usd"] > 0
    assert "match_rate_pct" in data
    assert "exceptions_by_category" in data
    assert "invoices_by_status" in data
    assert isinstance(data["top_carriers"], list)


def test_api_carriers(api_test_client):
    client, db = api_test_client
    resp = client.get("/api/v1/carriers")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 5
    assert "carrier_id" in data[0]
    assert "carrier_name" in data[0]


def test_api_list_invoices_and_pagination(api_test_client):
    client, db = api_test_client
    resp = client.get("/api/v1/invoices?page=1&page_size=10")
    assert resp.status_code == 200
    data = resp.json()

    assert data["total"] == 25
    assert data["page"] == 1
    assert data["page_size"] == 10
    assert len(data["items"]) == 10
    first_inv = data["items"][0]
    assert "invoice_id" in first_inv
    assert "billed_total" in first_inv
    assert "validation_status" in first_inv


def test_api_invoice_detail(api_test_client):
    client, db = api_test_client
    list_resp = client.get("/api/v1/invoices?page=1&page_size=1")
    inv_id = list_resp.json()["items"][0]["invoice_id"]

    resp = client.get(f"/api/v1/invoices/{inv_id}")
    assert resp.status_code == 200
    data = resp.json()

    assert data["invoice_id"] == inv_id
    assert "lines" in data
    assert len(data["lines"]) > 0
    assert "carrier_name" in data
    assert "exceptions" in data


def test_api_trigger_invoice_validation(api_test_client):
    client, db = api_test_client
    list_resp = client.get("/api/v1/invoices?page=1&page_size=1")
    inv_id = list_resp.json()["items"][0]["invoice_id"]

    resp = client.post(f"/api/v1/invoices/{inv_id}/validate?actor=QA_TESTER")
    assert resp.status_code == 200
    data = resp.json()

    assert data["invoice_id"] == inv_id
    assert data["overall_verdict"] in ["PASSED", "FAILED", "REVIEW_REQUIRED"]
    assert "billed_total" in data
    assert "expected_total" in data
    assert "variance_amount" in data


def test_api_invoice_traceability(api_test_client):
    client, db = api_test_client
    list_resp = client.get("/api/v1/invoices?page=1&page_size=1")
    inv_id = list_resp.json()["items"][0]["invoice_id"]

    resp = client.get(f"/api/v1/invoices/{inv_id}/traceability")
    assert resp.status_code == 200
    data = resp.json()

    assert data["invoice_id"] == inv_id
    assert "invoice_lines" in data
    assert "audit_events" in data
    assert "status_history" in data


def test_api_exceptions_workflow(api_test_client):
    client, db = api_test_client
    resp = client.get("/api/v1/exceptions?exception_status=OPEN&limit=10")
    assert resp.status_code == 200
    exceptions = resp.json()
    assert isinstance(exceptions, list)

    if exceptions:
        exc_id = exceptions[0]["exception_id"]
        # Transition exception status to UNDER_REVIEW
        patch_resp = client.patch(
            f"/api/v1/exceptions/{exc_id}/status",
            json={"target_status": "UNDER_REVIEW", "reason": "Investigation initiated by auditor"}
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["new_status"] == "UNDER_REVIEW"

        # Record manual override
        override_resp = client.post(
            f"/api/v1/exceptions/{exc_id}/override",
            json={"approved_amount": 25.0, "reason": "Approved commercial goodwill credit"}
        )
        assert override_resp.status_code == 200
        assert override_resp.json()["approved_amount"] == 25.0


def test_api_credit_notes_and_validation(api_test_client):
    client, db = api_test_client
    resp = client.get("/api/v1/credit-notes?limit=10")
    assert resp.status_code == 200
    cns = resp.json()
    assert isinstance(cns, list)

    if cns:
        cn_id = cns[0]["credit_note_id"]
        val_resp = client.post(f"/api/v1/credit-notes/{cn_id}/validate")
        assert val_resp.status_code == 200
        assert "is_valid" in val_resp.json()
        assert "reconciliation_status" in val_resp.json()


def test_api_audit_events(api_test_client):
    client, db = api_test_client
    resp = client.get("/api/v1/audit-events?limit=25")
    assert resp.status_code == 200
    events = resp.json()
    assert isinstance(events, list)
    assert len(events) > 0
    assert "event_id" in events[0]
    assert "event_type" in events[0]


def test_api_evaluation_report(api_test_client):
    client, db = api_test_client
    resp = client.get("/api/v1/evaluation")
    assert resp.status_code == 200
    data = resp.json()

    assert "metrics" in data
    assert "accuracy" in data["metrics"]
    assert "precision" in data["metrics"]
    assert "recall" in data["metrics"]
    assert "f1_score" in data["metrics"]
    assert "summary" in data
    assert "financial_impact" in data
    assert "scenario_breakdown" in data


def test_api_health_and_readiness(api_test_client):
    client, _ = api_test_client
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "HEALTHY"

    ready_resp = client.get("/ready")
    assert ready_resp.status_code == 200
    assert ready_resp.json()["ready"] is True

    api_health = client.get("/api/health")
    assert api_health.status_code == 200
    assert api_health.json()["status"] == "HEALTHY"


def test_api_rate_cards_and_lanes(api_test_client):
    client, _ = api_test_client
    rc_resp = client.get("/api/v1/rate-cards")
    assert rc_resp.status_code == 200
    cards = rc_resp.json()
    assert isinstance(cards, list)
    assert len(cards) > 0
    assert "rate_card_id" in cards[0]
    assert "base_rate" in cards[0]

    first_rc_id = cards[0]["rate_card_id"]
    rc_detail = client.get(f"/api/v1/rate-cards/{first_rc_id}")
    assert rc_detail.status_code == 200
    assert rc_detail.json()["rate_card_id"] == first_rc_id

    lane_resp = client.get("/api/v1/lanes")
    assert lane_resp.status_code == 200
    lanes = lane_resp.json()
    assert isinstance(lanes, list)
    assert len(lanes) > 0
    assert "lane_id" in lanes[0]


def test_api_shipments(api_test_client):
    client, _ = api_test_client
    resp = client.get("/api/v1/shipments?limit=10")
    assert resp.status_code == 200
    ships = resp.json()
    assert isinstance(ships, list)
    assert len(ships) > 0
    assert "shipment_id" in ships[0]
    assert "chargeable_weight_kg" in ships[0]

    first_shp_id = ships[0]["shipment_id"]
    detail_resp = client.get(f"/api/v1/shipments/{first_shp_id}")
    assert detail_resp.status_code == 200
    shp_data = detail_resp.json()
    assert shp_data["shipment_id"] == first_shp_id
    assert "dimensions" in shp_data
    assert "weights" in shp_data


def test_api_batch_validation(api_test_client):
    client, _ = api_test_client
    resp = client.post("/api/v1/invoices/validate-batch", json={"actor": "TEST_RUNNER"})
    assert resp.status_code == 200
    data = resp.json()
    assert "total_audited" in data
    assert "passed_count" in data
    assert "failed_count" in data
    assert "total_variance_recovered_usd" in data
    assert "duration_seconds" in data


def test_api_dataset_quality_and_manifest(api_test_client):
    client, _ = api_test_client
    q_resp = client.get("/api/v1/dataset/quality-report")
    assert q_resp.status_code == 200
    q_data = q_resp.json()
    assert "dataset_status" in q_data
    assert "stage_results" in q_data

    m_resp = client.get("/api/v1/dataset/manifest")
    assert m_resp.status_code == 200
    m_data = m_resp.json()
    assert "dataset_version" in m_data
    assert "entities" in m_data


def test_api_report_downloads(api_test_client):
    client, _ = api_test_client
    resp = client.get("/api/v1/reports/download/validation_summary.json")
    assert resp.status_code == 200
    assert len(resp.content) > 0

    resp_m = client.get("/api/v1/reports/download/manifest.json")
    assert resp_m.status_code == 200
    assert len(resp_m.content) > 0

