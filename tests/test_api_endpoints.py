import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app.core.database import Base
from backend.app.generator.generator import SyntheticDataGenerator
from backend.app.engine.validator import InvoiceValidator
from backend.app.api.routes.api import (
    get_dashboard_kpis, list_invoices, get_invoice_detail, run_evaluation, list_exceptions, list_credit_notes
)

@pytest.fixture(scope="module")
def api_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    gen = SyntheticDataGenerator(seed=20261022)
    gen.generate_all(db, num_carriers=5, num_shipments=20, num_invoices=15)
    
    # Run validation
    from backend.app.models.invoice import InvoiceHeader
    for inv in db.query(InvoiceHeader).all():
        InvoiceValidator.validate_invoice(db, inv.id)
    
    yield db
    db.close()

def test_api_dashboard_kpis(api_db):
    kpis = get_dashboard_kpis(db=api_db)
    assert kpis.total_invoices == 15
    assert kpis.total_billed_usd > 0
    assert kpis.match_rate_pct >= 0.0

def test_api_list_invoices(api_db):
    res = list_invoices(db=api_db, limit=10, offset=0)
    assert res["total"] == 15
    assert len(res["items"]) == 10
    assert "invoice_number" in res["items"][0]

def test_api_invoice_detail(api_db):
    res = list_invoices(db=api_db, limit=1, offset=0)
    inv_id = res["items"][0]["id"]
    detail = get_invoice_detail(invoice_id=inv_id, db=api_db)
    assert detail["id"] == inv_id
    assert "lines" in detail
    assert "carrier_code" in detail

def test_api_evaluation(api_db):
    eval_res = run_evaluation(db=api_db)
    assert "metrics" in eval_res
    assert eval_res["metrics"]["accuracy"] > 0.8
    assert "scenario_breakdown" in eval_res

def test_api_list_exceptions(api_db):
    exceptions = list_exceptions(db=api_db, limit=50)
    assert isinstance(exceptions, list)
    if exceptions:
        assert hasattr(exceptions[0], "category")
        assert hasattr(exceptions[0], "severity")

def test_api_list_credit_notes(api_db):
    cns = list_credit_notes(db=api_db)
    assert isinstance(cns, list)
