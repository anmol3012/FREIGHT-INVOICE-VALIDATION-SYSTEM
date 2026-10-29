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

from backend.app.core.database import Base, get_db
from backend.app.main import app
from backend.app.generator.generator import SyntheticDataGenerator
from backend.app.engine.validator import InvoiceValidator


@pytest.fixture(scope="module")
def api_test_client():
    """Sets up an in-memory SQLite database seeded with starter generator profile."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine)
    db = TestingSessionLocal()

    # Generate test dataset
    generator = SyntheticDataGenerator(profile_name="test", seed=20261022)
    generator.generate_all(db)

    # Validate all invoices
    from backend.app.models.invoice import FreightInvoice
    for inv in db.query(FreightInvoice).all():
        InvoiceValidator.validate_invoice(db, inv.invoice_id)

    # Dependency override
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    yield client, db

    app.dependency_overrides.clear()
    db.close()


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
    resp = client.get("/api/v1/exceptions?limit=10")
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
    assert "confusion_matrix" in data
    assert "financial_metrics" in data
    assert "scenario_breakdown" in data
