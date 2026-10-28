from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.app.core.database import get_db
from backend.app.core.config import settings
from backend.app.models.carrier import Carrier
from backend.app.models.shipment import Shipment
from backend.app.models.invoice import InvoiceHeader, InvoiceLine
from backend.app.models.exception import InvoiceException
from backend.app.models.credit_note import CreditNote
from backend.app.models.audit import AuditEvent
from backend.app.schemas.api_schemas import (
    InvoiceHeaderOut, InvoiceExceptionOut, CreditNoteOut, AuditEventOut, DashboardKPIs
)
from backend.app.engine.validator import InvoiceValidator
from backend.app.engine.evaluator import AuditEvaluator
from backend.app.generator.generator import SyntheticDataGenerator
from backend.app.generator.exporter import DataExporter

router = APIRouter()

@router.get("/dashboard/kpis", response_model=DashboardKPIs)
def get_dashboard_kpis(db: Session = Depends(get_db)):
    total_inv = db.query(InvoiceHeader).count()
    matched = db.query(InvoiceHeader).filter(InvoiceHeader.status == "VALIDATED_MATCH").count()
    disputed = db.query(InvoiceHeader).filter(InvoiceHeader.status.in_(["EXCEPTION_DISPUTED", "REJECTED"])).count()
    paid = db.query(InvoiceHeader).filter(InvoiceHeader.status == "PAID").count()
    
    total_billed = db.query(func.sum(InvoiceHeader.total_billed_amount)).scalar() or 0.0
    total_expected = db.query(func.sum(InvoiceHeader.calculated_expected_amount)).scalar() or 0.0
    
    # Overbilling detected (discrepancy recovery)
    variance_sum = db.query(func.sum(InvoiceHeader.total_variance_amount)).filter(InvoiceHeader.total_variance_amount > 0).scalar() or 0.0

    match_rate = round((matched / max(1, total_inv)) * 100.0, 1)

    # Categories breakdown
    exc_cats = db.query(InvoiceException.category, func.count(InvoiceException.id)).group_by(InvoiceException.category).all()
    categories_dict = {cat: count for cat, count in exc_cats}

    # Status breakdown
    statuses = db.query(InvoiceHeader.status, func.count(InvoiceHeader.id)).group_by(InvoiceHeader.status).all()
    status_dict = {st: count for st, count in statuses}

    return DashboardKPIs(
        total_invoices=total_inv,
        validated_match_count=matched,
        exception_disputed_count=disputed,
        paid_count=paid,
        match_rate_pct=match_rate,
        total_billed_usd=round(total_billed, 2),
        total_expected_usd=round(total_expected, 2),
        total_variance_recovered_usd=round(variance_sum, 2),
        exceptions_by_category=categories_dict,
        invoices_by_status=status_dict
    )

@router.get("/invoices")
def list_invoices(
    db: Session = Depends(get_db),
    status: Optional[str] = None,
    validation_status: Optional[str] = None,
    is_duplicate: Optional[bool] = None,
    search: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    query = db.query(InvoiceHeader)
    if status:
        query = query.filter(InvoiceHeader.status == status)
    if validation_status:
        query = query.filter(InvoiceHeader.validation_status == validation_status)
    if is_duplicate is not None:
        query = query.filter(InvoiceHeader.is_duplicate == is_duplicate)
    if search:
        search_fmt = f"%{search.strip()}%"
        query = query.filter(
            (InvoiceHeader.invoice_number.ilike(search_fmt)) |
            (InvoiceHeader.bol_number_billed.ilike(search_fmt))
        )

    total_count = query.count()
    invoices = query.order_by(InvoiceHeader.id.desc()).offset(offset).limit(limit).all()

    # Hydrate carrier code & name
    res = []
    for inv in invoices:
        inv_dict = {
            "id": inv.id,
            "invoice_number": inv.invoice_number,
            "carrier_id": inv.carrier_id,
            "carrier_code": inv.carrier.carrier_code if inv.carrier else "",
            "carrier_name": inv.carrier.name if inv.carrier else "",
            "shipment_id": inv.shipment_id,
            "bol_number_billed": inv.bol_number_billed,
            "invoice_date": inv.invoice_date,
            "due_date": inv.due_date,
            "currency": inv.currency,
            "total_billed_amount": inv.total_billed_amount,
            "calculated_expected_amount": inv.calculated_expected_amount,
            "total_variance_amount": inv.total_variance_amount,
            "status": inv.status,
            "validation_status": inv.validation_status,
            "is_duplicate": inv.is_duplicate,
            "duplicate_of_invoice_id": inv.duplicate_of_invoice_id,
            "reconciliation_notes": inv.reconciliation_notes,
            "created_at": inv.created_at,
            "validated_at": inv.validated_at,
            "lines_count": len(inv.lines),
            "exceptions_count": len(inv.exceptions)
        }
        res.append(inv_dict)

    return {"total": total_count, "items": res, "limit": limit, "offset": offset}

@router.get("/invoices/{invoice_id}")
def get_invoice_detail(invoice_id: int, db: Session = Depends(get_db)):
    inv = db.query(InvoiceHeader).filter(InvoiceHeader.id == invoice_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")

    lines_out = []
    for l in inv.lines:
        lines_out.append({
            "id": l.id,
            "line_number": l.line_number,
            "charge_type": l.charge_type,
            "charge_code": l.charge_code,
            "description": l.description,
            "billed_units": l.billed_units,
            "billed_rate": l.billed_rate,
            "billed_amount": l.billed_amount,
            "expected_units": l.expected_units,
            "expected_rate": l.expected_rate,
            "expected_amount": l.expected_amount,
            "variance_amount": l.variance_amount,
            "status": l.status,
            "discrepancy_reason": l.discrepancy_reason
        })

    exceptions_out = []
    for e in inv.exceptions:
        exceptions_out.append({
            "id": e.id,
            "category": e.category,
            "severity": e.severity,
            "billed_amount": e.billed_amount,
            "expected_amount": e.expected_amount,
            "variance_amount": e.variance_amount,
            "status": e.status,
            "root_cause_code": e.root_cause_code,
            "explanation": e.explanation,
            "resolved_by": e.resolved_by,
            "resolution_notes": e.resolution_notes
        })

    shipment_data = None
    if inv.shipment:
        s = inv.shipment
        wm = s.weight_measurements[0] if s.weight_measurements else None
        dr = s.delivery_record
        shipment_data = {
            "id": s.id,
            "bol_number": s.bol_number,
            "origin": f"{s.origin_city}, {s.origin_state} ({s.origin_zip})",
            "destination": f"{s.destination_city}, {s.destination_state} ({s.destination_zip})",
            "distance_miles": s.distance_miles,
            "pickup_date": str(s.pickup_date),
            "delivery_date": str(s.delivery_date),
            "dock_type": s.dock_type,
            "gross_weight_lbs": wm.gross_weight_lbs if wm else None,
            "billable_weight_lbs": wm.billable_weight_lbs if wm else None,
            "liftgate_actually_used": dr.liftgate_actually_used if dr else False,
            "dwell_minutes_recorded": dr.detention_minutes_recorded if dr else 0
        }

    return {
        "id": inv.id,
        "invoice_number": inv.invoice_number,
        "carrier_code": inv.carrier.carrier_code if inv.carrier else "",
        "carrier_name": inv.carrier.name if inv.carrier else "",
        "bol_number_billed": inv.bol_number_billed,
        "invoice_date": inv.invoice_date,
        "due_date": inv.due_date,
        "currency": inv.currency,
        "total_billed_amount": inv.total_billed_amount,
        "calculated_expected_amount": inv.calculated_expected_amount,
        "total_variance_amount": inv.total_variance_amount,
        "status": inv.status,
        "validation_status": inv.validation_status,
        "is_duplicate": inv.is_duplicate,
        "duplicate_of_invoice_id": inv.duplicate_of_invoice_id,
        "reconciliation_notes": inv.reconciliation_notes,
        "created_at": inv.created_at,
        "validated_at": inv.validated_at,
        "shipment": shipment_data,
        "lines": lines_out,
        "exceptions": exceptions_out
    }

@router.post("/invoices/{invoice_id}/validate")
def validate_single_invoice(invoice_id: int, db: Session = Depends(get_db)):
    try:
        updated = InvoiceValidator.validate_invoice(db, invoice_id, actor="OPERATOR_API")
        return {"success": True, "invoice_id": updated.id, "status": updated.status, "validation_status": updated.validation_status}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/invoices/validate-all")
def validate_all_invoices(db: Session = Depends(get_db)):
    invoices = db.query(InvoiceHeader).all()
    passed = 0
    failed = 0
    for inv in invoices:
        v = InvoiceValidator.validate_invoice(db, inv.id, actor="BATCH_AUDITOR")
        if v.validation_status == "PASSED":
            passed += 1
        else:
            failed += 1
    return {"total_audited": len(invoices), "passed": passed, "discrepancies_raised": failed}

@router.get("/exceptions", response_model=List[InvoiceExceptionOut])
def list_exceptions(
    db: Session = Depends(get_db),
    status: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500)
):
    query = db.query(InvoiceException)
    if status:
        query = query.filter(InvoiceException.status == status)
    if category:
        query = query.filter(InvoiceException.category == category)
    return query.order_by(InvoiceException.id.desc()).limit(limit).all()

@router.patch("/exceptions/{exception_id}")
def update_exception_status(
    exception_id: int,
    status: str = Query(..., pattern="^(OPEN|UNDER_REVIEW|APPROVED_OVERRIDE|DISPUTED|AUTO_RESOLVED)$"),
    resolution_notes: Optional[str] = None,
    db: Session = Depends(get_db)
):
    exc = db.query(InvoiceException).filter(InvoiceException.id == exception_id).first()
    if not exc:
        raise HTTPException(status_code=404, detail="Exception not found")

    exc.status = status
    exc.resolution_notes = resolution_notes
    exc.resolved_by = "OPERATOR_DASHBOARD"
    exc.resolved_at = func.now()

    # If approved override, check if all exceptions on invoice are cleared
    inv = exc.invoice
    if status == "APPROVED_OVERRIDE":
        all_cleared = all(e.status in ["APPROVED_OVERRIDE", "AUTO_RESOLVED"] for e in inv.exceptions)
        if all_cleared:
            inv.status = "EXCEPTION_APPROVED"
            inv.reconciliation_notes = (inv.reconciliation_notes or "") + " [Exceptions approved by operator override]"
    elif status == "DISPUTED":
        inv.status = "EXCEPTION_DISPUTED"

    db.commit()
    return {"success": True, "exception_id": exc.id, "status": exc.status}

@router.get("/credit-notes")
def list_credit_notes(db: Session = Depends(get_db)):
    cns = db.query(CreditNote).order_by(CreditNote.id.desc()).all()
    res = []
    for cn in cns:
        res.append({
            "id": cn.id,
            "credit_note_number": cn.credit_note_number,
            "carrier_id": cn.carrier_id,
            "carrier_code": cn.carrier.carrier_code if cn.carrier else "",
            "original_invoice_id": cn.original_invoice_id,
            "original_invoice_number": cn.original_invoice.invoice_number if cn.original_invoice else "",
            "issue_date": str(cn.issue_date),
            "credit_amount": cn.credit_amount,
            "applied_amount": cn.applied_amount,
            "remaining_balance": cn.remaining_balance,
            "status": cn.status,
            "reason_code": cn.reason_code,
            "rejection_reason": cn.rejection_reason
        })
    return res

@router.post("/credit-notes/{credit_note_id}/reconcile")
def reconcile_credit_note(credit_note_id: int, db: Session = Depends(get_db)):
    try:
        cn = InvoiceValidator.validate_credit_note(db, credit_note_id, actor="OPERATOR_API")
        return {"success": True, "credit_note_id": cn.id, "status": cn.status, "rejection_reason": cn.rejection_reason}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/evaluation")
def run_evaluation(db: Session = Depends(get_db)):
    return AuditEvaluator.evaluate(db)

@router.get("/audit-events", response_model=List[AuditEventOut])
def list_audit_events(db: Session = Depends(get_db), limit: int = Query(50, ge=1, le=200)):
    return db.query(AuditEvent).order_by(AuditEvent.id.desc()).limit(limit).all()

@router.post("/dataset/seed")
def trigger_seed(scale: str = "starter", reset: bool = True, db: Session = Depends(get_db)):
    from backend.app.cli import init_db
    init_db(reset=reset)
    num_c = settings.FULL_CARRIERS if scale == "full" else settings.STARTER_CARRIERS
    num_s = settings.FULL_SHIPMENTS if scale == "full" else settings.STARTER_SHIPMENTS
    num_i = settings.FULL_INVOICES if scale == "full" else settings.STARTER_INVOICES
    
    gen = SyntheticDataGenerator(seed=settings.DEFAULT_RANDOM_SEED)
    counts = gen.generate_all(db, num_carriers=num_c, num_shipments=num_s, num_invoices=num_i)
    return {"message": "Dataset generated successfully", "counts": counts}

@router.get("/dataset/export")
def trigger_export(db: Session = Depends(get_db)):
    exporter = DataExporter()
    return exporter.export_all(db)
