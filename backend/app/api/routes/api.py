"""
FastAPI REST API Routes for Freight Invoice Validation System (Phase 5).
Provides endpoints for Dashboard KPIs, Invoices, Validation Execution,
Audit Exceptions, Credit Notes, Historical Traceability, and Offline Accuracy Evaluation.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from pathlib import Path
import json
import time
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, or_

from backend.app.core.database import get_db
from backend.app.models.carrier import Carrier
from backend.app.models.lane import Lane
from backend.app.models.rate_card import RateCard, RateTier
from backend.app.models.shipment import Shipment
from backend.app.models.invoice import FreightInvoice, InvoiceLine
from backend.app.models.audit_exception import AuditException
from backend.app.models.credit_note import CreditNote
from backend.app.models.audit import AuditEvent, EntityStatusHistory
from backend.app.models.enums import (
    InvoiceStatus, ValidationStatus, ExceptionStatus, ExceptionSeverity,
    CreditNoteApprovalStatus, CreditNoteReconciliationStatus
)
from backend.app.schemas.api_schemas import (
    DashboardKPIs, FreightInvoiceSummaryOut, FreightInvoiceDetailOut,
    PaginatedInvoicesOut, ValidationTriggerResponse, AuditExceptionOut,
    CreditNoteOut, AuditEventOut, ExceptionStatusUpdateRequest,
    ManualOverrideRequest, CreditNoteValidateRequest, TraceabilityResponse,
    EvaluationReportOut, CarrierOut, InvoiceLineOut,
    HealthCheckResponse, ReadinessResponse, DatasetGenerateRequest,
    DatasetGenerateResponse, BatchValidationRequest, BatchValidationResponse,
    RateCardOut, LaneOut, ShipmentOut
)
from backend.app.engine.validator import FreightInvoiceValidator
from backend.app.engine.evaluator import AuditEvaluator
from backend.app.engine.history_service import HistoryService
from backend.app.engine.audit_service import AuditService
from backend.app.engine.credit_note_service import CreditNoteService
from backend.app.generator.generator import DeterministicDataGenerator
from backend.app.generator.data_quality import DataQualityValidator

router = APIRouter()


# ============================================================================
# 1. Dashboard KPIs & Carrier Endpoints
# ============================================================================

@router.get("/dashboard/kpis", response_model=DashboardKPIs)
def get_dashboard_kpis(db: Session = Depends(get_db)):
    """Computes real-time executive KPIs from operational invoice and exception stores."""
    total_invoices = db.query(FreightInvoice).count()
    validated_match = db.query(FreightInvoice).filter(
        FreightInvoice.validation_status == ValidationStatus.PASSED
    ).count()
    exception_disputed = db.query(FreightInvoice).filter(
        FreightInvoice.validation_status == ValidationStatus.FAILED
    ).count()
    pending_audit = db.query(FreightInvoice).filter(
        FreightInvoice.validation_status == ValidationStatus.UNAUDITED
    ).count()
    paid_count = db.query(FreightInvoice).filter(
        FreightInvoice.invoice_status == InvoiceStatus.PAID
    ).count()
    rejected_count = db.query(FreightInvoice).filter(
        FreightInvoice.invoice_status == InvoiceStatus.REJECTED
    ).count()

    total_billed = db.query(func.sum(FreightInvoice.billed_total)).scalar() or 0.0
    total_expected = db.query(func.sum(FreightInvoice.expected_total)).scalar() or 0.0

    # Overbilling detected (discrepancy recovery)
    variance_sum = db.query(func.sum(FreightInvoice.variance_amount)).filter(
        FreightInvoice.variance_amount > 0
    ).scalar() or 0.0

    match_rate = round((validated_match / max(1, total_invoices)) * 100.0, 1)

    # Categories breakdown from AuditException
    exc_cats = db.query(
        AuditException.exception_type,
        func.count(AuditException.exception_id)
    ).group_by(AuditException.exception_type).all()
    categories_dict = {
        (cat.value if hasattr(cat, "value") else str(cat)): count
        for cat, count in exc_cats
    }

    # Invoices by Status
    statuses = db.query(
        FreightInvoice.invoice_status,
        func.count(FreightInvoice.invoice_id)
    ).group_by(FreightInvoice.invoice_status).all()
    status_dict = {
        (st.value if hasattr(st, "value") else str(st)): count
        for st, count in statuses
    }

    # Top carriers by volume
    top_carriers_query = db.query(
        Carrier.carrier_id,
        Carrier.carrier_code,
        Carrier.carrier_name,
        func.count(FreightInvoice.invoice_id).label("invoice_count"),
        func.sum(FreightInvoice.billed_total).label("total_billed"),
        func.sum(FreightInvoice.variance_amount).label("total_variance")
    ).join(FreightInvoice, Carrier.carrier_id == FreightInvoice.carrier_id)\
     .group_by(Carrier.carrier_id)\
     .order_by(desc("total_billed"))\
     .limit(5).all()

    top_carriers = [
        {
            "carrier_id": c_id,
            "carrier_code": code,
            "carrier_name": name,
            "invoice_count": inv_cnt,
            "total_billed": round(billed or 0.0, 2),
            "total_variance": round(var or 0.0, 2)
        }
        for c_id, code, name, inv_cnt, billed, var in top_carriers_query
    ]

    return DashboardKPIs(
        total_invoices=total_invoices,
        validated_match_count=validated_match,
        exception_disputed_count=exception_disputed,
        pending_audit_count=pending_audit,
        paid_count=paid_count,
        rejected_count=rejected_count,
        match_rate_pct=match_rate,
        total_billed_usd=round(total_billed, 2),
        total_expected_usd=round(total_expected, 2),
        total_variance_recovered_usd=round(variance_sum, 2),
        exceptions_by_category=categories_dict,
        invoices_by_status=status_dict,
        top_carriers=top_carriers
    )


@router.get("/carriers", response_model=List[CarrierOut])
def list_carriers(db: Session = Depends(get_db)):
    """Returns active carriers for filtering and directory lookup."""
    return db.query(Carrier).order_by(Carrier.carrier_name).all()


# ============================================================================
# 2. Invoices & Validation Endpoints
# ============================================================================

@router.get("/invoices", response_model=PaginatedInvoicesOut)
def list_invoices(
    carrier_id: Optional[str] = Query(None, description="Filter by carrier ID"),
    invoice_status: Optional[str] = Query(None, description="Filter by invoice status"),
    validation_status: Optional[str] = Query(None, description="Filter by validation status"),
    search: Optional[str] = Query(None, description="Search invoice number or shipment reference"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(25, ge=1, le=200, description="Items per page"),
    db: Session = Depends(get_db)
):
    """Lists freight invoices with filtering, full-text search, and pagination."""
    query = db.query(FreightInvoice)

    if carrier_id:
        query = query.filter(FreightInvoice.carrier_id == carrier_id)
    if invoice_status:
        query = query.filter(FreightInvoice.invoice_status == invoice_status)
    if validation_status:
        query = query.filter(FreightInvoice.validation_status == validation_status)
    if search:
        search_pattern = f"%{search.strip()}%"
        query = query.filter(
            or_(
                FreightInvoice.invoice_number.ilike(search_pattern),
                FreightInvoice.raw_shipment_reference.ilike(search_pattern)
            )
        )

    total = query.count()
    offset = (page - 1) * page_size
    invoices = query.order_by(desc(FreightInvoice.invoice_date))\
                    .offset(offset)\
                    .limit(page_size)\
                    .all()

    items = []
    for inv in invoices:
        carrier = inv.carrier
        items.append(
            FreightInvoiceSummaryOut(
                invoice_id=inv.invoice_id,
                carrier_id=inv.carrier_id,
                carrier_code=carrier.carrier_code if carrier else None,
                carrier_name=carrier.carrier_name if carrier else None,
                shipment_id=inv.shipment_id,
                raw_shipment_reference=inv.raw_shipment_reference,
                invoice_number=inv.invoice_number,
                invoice_date=inv.invoice_date,
                service_period_start=inv.service_period_start,
                service_period_end=inv.service_period_end,
                due_date=inv.due_date,
                currency=inv.currency,
                billed_total=round(inv.billed_total, 2),
                expected_total=round(inv.expected_total, 2),
                variance_amount=round(inv.variance_amount, 2),
                invoice_status=inv.invoice_status.value if hasattr(inv.invoice_status, "value") else str(inv.invoice_status),
                validation_status=inv.validation_status.value if hasattr(inv.validation_status, "value") else str(inv.validation_status),
                duplicate_group_id=inv.duplicate_group_id,
                fingerprint_hash=inv.fingerprint_hash,
                exception_count=len(inv.audit_exceptions) if inv.audit_exceptions else 0,
                created_at=inv.created_at
            )
        )

    return PaginatedInvoicesOut(
        total=total,
        page=page,
        page_size=page_size,
        items=items
    )


@router.get("/invoices/{invoice_id}", response_model=FreightInvoiceDetailOut)
def get_invoice_detail(invoice_id: str, db: Session = Depends(get_db)):
    """Retrieves full invoice details including lines, detected exceptions, and credit notes."""
    inv = db.query(FreightInvoice).filter(FreightInvoice.invoice_id == invoice_id).first()
    if not inv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Invoice '{invoice_id}' not found.")

    carrier = inv.carrier

    lines_out = [
        InvoiceLineOut(
            invoice_line_id=line.invoice_line_id,
            invoice_id=line.invoice_id,
            line_number=line.line_number,
            line_type=line.line_type.value if hasattr(line.line_type, "value") else str(line.line_type),
            accessorial_id=line.accessorial_id,
            description=line.description,
            quantity=line.quantity,
            unit_of_measure=line.unit_of_measure,
            unit_rate=line.unit_rate,
            billed_amount=round(line.billed_amount, 2),
            expected_amount=round(line.expected_amount, 2),
            variance_amount=round(line.variance_amount, 2),
            evidence_reference=line.evidence_reference,
            source_reference=line.source_reference,
            created_at=line.created_at
        )
        for line in sorted(inv.invoice_lines, key=lambda l: l.line_number)
    ]

    exceptions_out = [
        AuditExceptionOut(
            exception_id=exc.exception_id,
            invoice_id=exc.invoice_id,
            invoice_line_id=exc.invoice_line_id,
            shipment_id=exc.shipment_id,
            exception_type=exc.exception_type.value if hasattr(exc.exception_type, "value") else str(exc.exception_type),
            severity=exc.severity.value if hasattr(exc.severity, "value") else str(exc.severity),
            expected_amount=round(exc.expected_amount, 2),
            billed_amount=round(exc.billed_amount, 2),
            disputed_amount=round(exc.disputed_amount, 2),
            currency=exc.currency,
            explanation=exc.explanation,
            evidence_json=exc.evidence_json,
            exception_status=exc.exception_status.value if hasattr(exc.exception_status, "value") else str(exc.exception_status),
            detected_at=exc.detected_at,
            resolved_at=exc.resolved_at
        )
        for exc in inv.audit_exceptions
    ]

    credit_notes_out = [
        CreditNoteOut(
            credit_note_id=cn.credit_note_id,
            credit_note_number=cn.credit_note_number,
            carrier_id=cn.carrier_id,
            invoice_id=cn.invoice_id,
            exception_id=cn.exception_id,
            issue_date=cn.issue_date,
            currency=cn.currency,
            credit_amount=round(cn.credit_amount, 2),
            approval_status=cn.approval_status.value if hasattr(cn.approval_status, "value") else str(cn.approval_status),
            reconciliation_status=cn.reconciliation_status.value if hasattr(cn.reconciliation_status, "value") else str(cn.reconciliation_status),
            created_at=cn.created_at
        )
        for cn in inv.credit_notes
    ]

    return FreightInvoiceDetailOut(
        invoice_id=inv.invoice_id,
        carrier_id=inv.carrier_id,
        carrier_code=carrier.carrier_code if carrier else None,
        carrier_name=carrier.carrier_name if carrier else None,
        shipment_id=inv.shipment_id,
        raw_shipment_reference=inv.raw_shipment_reference,
        invoice_number=inv.invoice_number,
        invoice_date=inv.invoice_date,
        service_period_start=inv.service_period_start,
        service_period_end=inv.service_period_end,
        due_date=inv.due_date,
        currency=inv.currency,
        billed_total=round(inv.billed_total, 2),
        expected_total=round(inv.expected_total, 2),
        variance_amount=round(inv.variance_amount, 2),
        invoice_status=inv.invoice_status.value if hasattr(inv.invoice_status, "value") else str(inv.invoice_status),
        validation_status=inv.validation_status.value if hasattr(inv.validation_status, "value") else str(inv.validation_status),
        duplicate_group_id=inv.duplicate_group_id,
        fingerprint_hash=inv.fingerprint_hash,
        exception_count=len(exceptions_out),
        created_at=inv.created_at,
        lines=lines_out,
        exceptions=exceptions_out,
        credit_notes=credit_notes_out
    )


@router.post("/invoices/{invoice_id}/validate", response_model=ValidationTriggerResponse)
def trigger_invoice_validation(
    invoice_id: str,
    actor: str = Query("API_USER", description="Actor triggering validation"),
    db: Session = Depends(get_db)
):
    """Executes the 20-step Freight Calculation and Validation Engine on the given invoice."""
    try:
        summary = FreightInvoiceValidator.validate_invoice(db, invoice_id, actor=actor)
        return ValidationTriggerResponse(
            invoice_id=summary.invoice_id,
            overall_verdict=summary.overall_verdict,
            validation_status=summary.validation_status.value if hasattr(summary.validation_status, "value") else str(summary.validation_status),
            invoice_status=summary.invoice_status.value if hasattr(summary.invoice_status, "value") else str(summary.invoice_status),
            billed_total=round(summary.billed_total, 2),
            expected_total=round(summary.expected_total, 2),
            variance_amount=round(summary.variance_amount, 2),
            exceptions_raised_count=summary.exceptions_raised_count,
            exception_ids=summary.exception_ids,
            diagnostic_messages=summary.diagnostic_messages
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Validation failed: {str(e)}")


@router.get("/invoices/{invoice_id}/traceability", response_model=TraceabilityResponse)
def get_invoice_traceability(invoice_id: str, db: Session = Depends(get_db)):
    """Returns end-to-end lineage, evidence records, and lifecycle transitions for audit trail verification."""
    try:
        data = HistoryService.get_invoice_traceability(db, invoice_id)
        inv_data = data["invoice"]
        return TraceabilityResponse(
            invoice_id=inv_data["invoice_id"],
            invoice_number=inv_data["invoice_number"],
            carrier=inv_data.get("carrier"),
            shipment=data.get("shipment"),
            rate_card=data.get("rate_card"),
            weight_measurements=data.get("weight_measurements", []),
            delivery_evidence=data.get("delivery_evidence"),
            invoice_lines=data.get("lines", []),
            exceptions=data.get("exceptions", []),
            credit_notes=data.get("credit_notes", []),
            status_history=data.get("lifecycle_transitions", []),
            audit_events=data.get("audit_events", [])
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# ============================================================================
# 3. Exceptions & Workflow Management
# ============================================================================

@router.get("/exceptions", response_model=List[AuditExceptionOut])
def list_exceptions(
    invoice_id: Optional[str] = Query(None, description="Filter by invoice ID"),
    exception_status: Optional[str] = Query(None, description="Filter by exception status"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    exception_type: Optional[str] = Query(None, description="Filter by exception type"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """Lists actionable audit exceptions with flexible filtering."""
    query = db.query(AuditException)

    if invoice_id:
        query = query.filter(AuditException.invoice_id == invoice_id)
    if exception_status:
        query = query.filter(AuditException.exception_status == exception_status)
    if severity:
        query = query.filter(AuditException.severity == severity)
    if exception_type:
        query = query.filter(AuditException.exception_type == exception_type)

    exceptions = query.order_by(desc(AuditException.detected_at))\
                      .offset(offset)\
                      .limit(limit)\
                      .all()

    return [
        AuditExceptionOut(
            exception_id=exc.exception_id,
            invoice_id=exc.invoice_id,
            invoice_line_id=exc.invoice_line_id,
            shipment_id=exc.shipment_id,
            exception_type=exc.exception_type.value if hasattr(exc.exception_type, "value") else str(exc.exception_type),
            severity=exc.severity.value if hasattr(exc.severity, "value") else str(exc.severity),
            expected_amount=round(exc.expected_amount, 2),
            billed_amount=round(exc.billed_amount, 2),
            disputed_amount=round(exc.disputed_amount, 2),
            currency=exc.currency,
            explanation=exc.explanation,
            evidence_json=exc.evidence_json,
            exception_status=exc.exception_status.value if hasattr(exc.exception_status, "value") else str(exc.exception_status),
            detected_at=exc.detected_at,
            resolved_at=exc.resolved_at
        )
        for exc in exceptions
    ]


@router.patch("/exceptions/{exception_id}/status")
def update_exception_status(
    exception_id: str,
    req: ExceptionStatusUpdateRequest,
    db: Session = Depends(get_db)
):
    """Transitions an exception through lifecycle states (e.g. UNDER_REVIEW, APPROVED, REJECTED, RESOLVED)."""
    exc = db.query(AuditException).filter(AuditException.exception_id == exception_id).first()
    if not exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Exception '{exception_id}' not found.")

    try:
        target_enum = ExceptionStatus(req.target_status)
        AuditService.transition_exception(
            db=db,
            exception=exc,
            target_status=target_enum,
            reason=req.reason,
            actor=req.actor
        )
        db.commit()
        return {
            "exception_id": exc.exception_id,
            "new_status": exc.exception_status.value,
            "resolved_at": exc.resolved_at
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/exceptions/{exception_id}/override")
def record_manual_override(
    exception_id: str,
    req: ManualOverrideRequest,
    db: Session = Depends(get_db)
):
    """Records an authorized manual override on a disputed variance."""
    exc = db.query(AuditException).filter(AuditException.exception_id == exception_id).first()
    if not exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Exception '{exception_id}' not found.")

    try:
        old_status = exc.exception_status.value if hasattr(exc.exception_status, "value") else str(exc.exception_status)
        exc.exception_status = ExceptionStatus.APPROVED_OVERRIDE
        exc.resolved_at = datetime.utcnow()

        AuditService.record_manual_override(
            db=db,
            entity_type="AuditException",
            entity_id=exc.exception_id,
            actor=req.actor,
            override_reason=req.reason,
            previous_decision=old_status,
            new_decision=ExceptionStatus.APPROVED_OVERRIDE.value,
            financial_delta=req.approved_amount
        )
        db.commit()
        return {
            "exception_id": exc.exception_id,
            "approved_amount": req.approved_amount,
            "status": exc.exception_status.value
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ============================================================================
# 4. Credit Notes Endpoints
# ============================================================================

@router.get("/credit-notes", response_model=List[CreditNoteOut])
def list_credit_notes(
    carrier_id: Optional[str] = Query(None, description="Filter by carrier ID"),
    invoice_id: Optional[str] = Query(None, description="Filter by invoice ID"),
    reconciliation_status: Optional[str] = Query(None, description="Filter by reconciliation status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """Lists carrier credit notes with reconciliation and approval tracking."""
    query = db.query(CreditNote)

    if carrier_id:
        query = query.filter(CreditNote.carrier_id == carrier_id)
    if invoice_id:
        query = query.filter(CreditNote.invoice_id == invoice_id)
    if reconciliation_status:
        query = query.filter(CreditNote.reconciliation_status == reconciliation_status)

    cns = query.order_by(desc(CreditNote.issue_date))\
               .offset(offset)\
               .limit(limit)\
               .all()

    return [
        CreditNoteOut(
            credit_note_id=cn.credit_note_id,
            credit_note_number=cn.credit_note_number,
            carrier_id=cn.carrier_id,
            invoice_id=cn.invoice_id,
            exception_id=cn.exception_id,
            issue_date=cn.issue_date,
            currency=cn.currency,
            credit_amount=round(cn.credit_amount, 2),
            approval_status=cn.approval_status.value if hasattr(cn.approval_status, "value") else str(cn.approval_status),
            reconciliation_status=cn.reconciliation_status.value if hasattr(cn.reconciliation_status, "value") else str(cn.reconciliation_status),
            created_at=cn.created_at
        )
        for cn in cns
    ]


@router.post("/credit-notes/{credit_note_id}/validate")
def validate_credit_note(
    credit_note_id: str,
    req: CreditNoteValidateRequest = CreditNoteValidateRequest(),
    db: Session = Depends(get_db)
):
    """Validates and reconciles credit note against remaining disputed balance (Scenario E enforcement)."""
    try:
        res = CreditNoteService.validate_credit_note(db, credit_note_id=credit_note_id, actor=req.actor)
        db.commit()
        return {
            "credit_note_id": res.credit_note_id,
            "credit_note_number": res.credit_note_number,
            "is_valid": res.is_valid,
            "approval_status": res.approval_status.value,
            "reconciliation_status": res.reconciliation_status.value,
            "credit_amount": res.credit_amount,
            "approved_disputed_balance": res.approved_disputed_balance,
            "remaining_balance_after_credit": res.remaining_balance_after_credit,
            "excess_amount": res.excess_amount,
            "explanation": res.explanation
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# ============================================================================
# 5. Audit Events & Offline Accuracy Evaluation
# ============================================================================

@router.get("/audit-events", response_model=List[AuditEventOut])
def list_audit_events(
    entity_type: Optional[str] = Query(None, description="Filter by entity type"),
    entity_id: Optional[str] = Query(None, description="Filter by entity ID"),
    actor: Optional[str] = Query(None, description="Filter by actor"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """Queries immutable, append-only audit trail events."""
    query = db.query(AuditEvent)

    if entity_type:
        query = query.filter(AuditEvent.entity_type == entity_type)
    if entity_id:
        query = query.filter(AuditEvent.entity_id == entity_id)
    if actor:
        query = query.filter(AuditEvent.actor == actor)

    events = query.order_by(desc(AuditEvent.timestamp))\
                  .offset(offset)\
                  .limit(limit)\
                  .all()

    return [
        AuditEventOut(
            event_id=ev.event_id,
            entity_type=ev.entity_type,
            entity_id=ev.entity_id,
            event_type=ev.event_type.value if hasattr(ev.event_type, "value") else str(ev.event_type),
            actor=ev.actor,
            notes=ev.notes,
            timestamp=ev.timestamp,
            payload_json=ev.payload_json
        )
        for ev in events
    ]


@router.get("/evaluation", response_model=EvaluationReportOut)
def run_evaluation(db: Session = Depends(get_db)):
    """
    Executes offline audit accuracy evaluation comparing operational validation
    outcomes against independently stored ground-truth anomaly labels.
    """
    report = AuditEvaluator.evaluate(db)
    if "error" in report:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=report["error"])

    return EvaluationReportOut(
        evaluated_at=datetime.utcnow(),
        summary=report["summary"],
        metrics=report["metrics"],
        financial_impact=report["financial_impact"],
        scenario_breakdown=report["scenario_breakdown"]
    )



# ============================================================================
# 6. Health, Readiness, and Dataset Management
# ============================================================================

@router.get("/health", response_model=HealthCheckResponse)
def api_health():
    """Health check endpoint for liveness probes."""
    return HealthCheckResponse(
        status="HEALTHY",
        database="CONNECTED",
        timestamp=datetime.utcnow()
    )


@router.get("/ready", response_model=ReadinessResponse)
def api_readiness(db: Session = Depends(get_db)):
    """Readiness probe confirming tables exist and database accepts queries."""
    total = db.query(FreightInvoice).count()
    return ReadinessResponse(
        ready=True,
        tables_initialized=True,
        total_invoices=total
    )


@router.post("/dataset/generate", response_model=DatasetGenerateResponse)
def generate_dataset(
    req: DatasetGenerateRequest = DatasetGenerateRequest(),
    db: Session = Depends(get_db)
):
    """Triggers synthetic dataset generation and automated validation on demand."""
    generator = DeterministicDataGenerator(profile_name=req.scale, seed=req.seed)
    counts = generator.generate_all(db)

    # Validate all generated invoices
    invoices = db.query(FreightInvoice).all()
    for inv in invoices:
      FreightInvoiceValidator.validate_invoice(db, inv.invoice_id)
    db.commit()

    return DatasetGenerateResponse(
        status="COMPLETED",
        scale=req.scale,
        seed=req.seed,
        counts=counts
    )


@router.get("/dataset/quality-report")
def get_dataset_quality_report(db: Session = Depends(get_db)):
    """Runs data-quality validation across all entities and returns the comprehensive audit summary."""
    validator = DataQualityValidator(db)
    return validator.run_all_checks()


@router.get("/dataset/manifest")
def get_dataset_manifest():
    """Returns the cryptographic SHA-256 source manifest and provenance."""
    manifest_path = Path("data/exports/manifest.json")
    if not manifest_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset manifest not found. Run export first.")
    with open(manifest_path, "r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================================
# 7. Master Entities (Carriers, RateCards, Lanes, Shipments)
# ============================================================================

@router.get("/carriers/{carrier_id}")
def get_carrier_detail(carrier_id: str, db: Session = Depends(get_db)):
    carrier = db.query(Carrier).filter(Carrier.carrier_id == carrier_id).first()
    if not carrier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Carrier '{carrier_id}' not found.")
    return {
        "carrier_id": carrier.carrier_id,
        "carrier_code": carrier.carrier_code,
        "carrier_name": carrier.carrier_name,
        "status": carrier.status.value,
        "country_code": carrier.country_code,
        "rate_card_count": len(carrier.rate_cards) if carrier.rate_cards else 0,
        "invoice_count": len(carrier.invoices) if carrier.invoices else 0
    }


@router.get("/rate-cards", response_model=List[RateCardOut])
def list_rate_cards(
    carrier_id: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    query = db.query(RateCard)
    if carrier_id:
        query = query.filter(RateCard.carrier_id == carrier_id)
    cards = query.all()
    return [
        RateCardOut(
            rate_card_id=rc.rate_card_id,
            carrier_id=rc.carrier_id,
            lane_id=rc.lane_id,
            service_level=rc.service_level.value if hasattr(rc.service_level, "value") else str(rc.service_level),
            currency=rc.currency,
            effective_from=rc.effective_from,
            effective_to=rc.effective_to,
            base_rate=rc.base_rate,
            minimum_charge=rc.minimum_charge,
            status=rc.status.value if hasattr(rc.status, "value") else str(rc.status),
            tier_count=len(rc.rate_tiers) if rc.rate_tiers else 0
        )
        for rc in cards
    ]


@router.get("/rate-cards/{rate_card_id}")
def get_rate_card_detail(rate_card_id: str, db: Session = Depends(get_db)):
    rc = db.query(RateCard).filter(RateCard.rate_card_id == rate_card_id).first()
    if not rc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"RateCard '{rate_card_id}' not found.")
    return {
        "rate_card_id": rc.rate_card_id,
        "carrier_id": rc.carrier_id,
        "lane_id": rc.lane_id,
        "service_level": rc.service_level.value if hasattr(rc.service_level, "value") else str(rc.service_level),
        "currency": rc.currency,
        "effective_from": rc.effective_from.isoformat() if rc.effective_from else None,
        "effective_to": rc.effective_to.isoformat() if rc.effective_to else None,
        "base_rate": rc.base_rate,
        "minimum_charge": rc.minimum_charge,
        "status": rc.status.value if hasattr(rc.status, "value") else str(rc.status),
        "tiers": [
            {
                "tier_id": t.rate_tier_id,
                "tier_sequence": t.tier_sequence,
                "min_weight_kg": t.min_weight_kg,
                "max_weight_kg": t.max_weight_kg,
                "rate_per_kg": t.rate_per_kg
            }
            for t in sorted(rc.rate_tiers, key=lambda x: x.tier_sequence)
        ]
    }


@router.get("/lanes", response_model=List[LaneOut])
def list_lanes(db: Session = Depends(get_db)):
    return db.query(Lane).all()


@router.get("/lanes/{lane_id}")
def get_lane_detail(lane_id: str, db: Session = Depends(get_db)):
    l = db.query(Lane).filter(Lane.lane_id == lane_id).first()
    if not l:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Lane '{lane_id}' not found.")
    return {
        "lane_id": l.lane_id,
        "origin_region": l.origin_region,
        "destination_region": l.destination_region,
        "standard_transit_days": l.standard_transit_days,
        "distance_km": l.distance_km,
        "status": l.status.value if hasattr(l.status, "value") else str(l.status)
    }


@router.get("/shipments", response_model=List[ShipmentOut])
def list_shipments(
    carrier_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    query = db.query(Shipment)
    if carrier_id:
        query = query.filter(Shipment.carrier_id == carrier_id)
    ships = query.offset(offset).limit(limit).all()
    return [
        ShipmentOut(
            shipment_id=s.shipment_id,
            carrier_id=s.carrier_id,
            lane_id=s.lane_id,
            service_level=s.service_level.value if hasattr(s.service_level, "value") else str(s.service_level),
            ship_date=s.ship_date,
            delivery_due_date=s.delivery_due_date,
            actual_length_cm=s.actual_length_cm,
            actual_width_cm=s.actual_width_cm,
            actual_height_cm=s.actual_height_cm,
            actual_weight_kg=s.actual_weight_kg,
            chargeable_weight_kg=s.chargeable_weight_kg,
            currency=s.currency,
            shipment_status=s.shipment_status.value if hasattr(s.shipment_status, "value") else str(s.shipment_status)
        )
        for s in ships
    ]


@router.get("/shipments/{shipment_id}")
def get_shipment_detail(shipment_id: str, db: Session = Depends(get_db)):
    s = db.query(Shipment).filter(Shipment.shipment_id == shipment_id).first()
    if not s:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Shipment '{shipment_id}' not found.")
    evidence = s.delivery_evidence
    return {
        "shipment_id": s.shipment_id,
        "carrier_id": s.carrier_id,
        "lane_id": s.lane_id,
        "service_level": s.service_level.value if hasattr(s.service_level, "value") else str(s.service_level),
        "ship_date": s.ship_date.isoformat(),
        "delivery_due_date": s.delivery_due_date.isoformat(),
        "dimensions": {
            "length_cm": s.actual_length_cm,
            "width_cm": s.actual_width_cm,
            "height_cm": s.actual_height_cm
        },
        "weights": {
            "actual_weight_kg": s.actual_weight_kg,
            "chargeable_weight_kg": s.chargeable_weight_kg
        },
        "delivery_evidence": {
            "delivered_at": evidence.delivered_at.isoformat(),
            "recipient_name": evidence.recipient_name,
            "signed_pod_ref": evidence.signed_pod_ref,
            "dock_type": evidence.facility_dock_type,
            "liftgate_used": evidence.liftgate_actually_used,
            "detention_minutes": evidence.detention_minutes_recorded
        } if evidence else None,
        "legs": [
            {
                "leg_id": leg.shipment_leg_id,
                "sequence": leg.leg_sequence,
                "origin": leg.origin_location_code,
                "destination": leg.destination_location_code
            }
            for leg in s.shipment_legs
        ]
    }


# ============================================================================
# 8. Batch Validation & Report Downloads
# ============================================================================

@router.post("/invoices/validate-batch", response_model=BatchValidationResponse)
def validate_invoices_batch(
    req: BatchValidationRequest = BatchValidationRequest(),
    db: Session = Depends(get_db)
):
    """Executes batch freight validation across all unaudited (or specified) invoices."""
    start_t = time.time()
    query = db.query(FreightInvoice)
    if req.invoice_ids:
        query = query.filter(FreightInvoice.invoice_id.in_(req.invoice_ids))
    else:
        query = query.filter(FreightInvoice.validation_status == ValidationStatus.UNAUDITED)

    invoices = query.all()
    passed = 0
    failed = 0
    recovered = 0.0

    for inv in invoices:
        res = FreightInvoiceValidator.validate_invoice(db, inv.invoice_id, actor=req.actor)
        if res.overall_verdict == "PASSED":
            passed += 1
        else:
            failed += 1
            recovered += max(0.0, res.variance_amount)

    db.commit()
    duration = round(time.time() - start_t, 3)
    return BatchValidationResponse(
        total_audited=len(invoices),
        passed_count=passed,
        failed_count=failed,
        total_variance_recovered_usd=round(recovered, 2),
        duration_seconds=duration
    )


@router.get("/reports/download/{filename}")
def download_report_file(filename: str):
    """Securely downloads generated dataset files and data quality reports."""
    allowed_dir = Path("data/exports")
    safe_file = (allowed_dir / filename).resolve()
    if not str(safe_file).startswith(str(allowed_dir.resolve())):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")
    if not safe_file.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"File '{filename}' not found.")
    return FileResponse(path=str(safe_file), filename=filename)


# ============================================================================
# 9. Dashboard Aliases & Compatibility Endpoints
# ============================================================================

@router.post("/invoices/validate-all")
def validate_all_invoices_alias(db: Session = Depends(get_db)):
    """Alias for batch invoice audit."""
    return validate_invoices_batch(req=BatchValidationRequest(), db=db)


@router.post("/dataset/seed")
def seed_dataset_alias(
    scale: str = Query("starter"),
    reset: bool = Query(False),
    seed: int = Query(20261022),
    db: Session = Depends(get_db)
):
    """Alias for dataset generation."""
    return generate_dataset(req=DatasetGenerateRequest(scale=scale, seed=seed, reset=reset), db=db)


@router.get("/dataset/export")
def export_dataset_alias(
    seed: int = Query(20261022),
    db: Session = Depends(get_db)
):
    """Alias for exporting data and checksums."""
    from backend.app.generator.exporter import DataExporter
    exporter = DataExporter()
    res = exporter.export_all(db, seed=seed)
    return res


@router.patch("/exceptions/{exception_id}")
def update_exception_status_alias(
    exception_id: str,
    status: str = Query(...),
    reason: str = Query("Auditor manual review update"),
    db: Session = Depends(get_db)
):
    """Alias for exception status transition."""
    return update_exception_status(
        exception_id=exception_id,
        req=ExceptionStatusUpdateRequest(target_status=status, reason=reason),
        db=db
    )


@router.post("/credit-notes/{credit_note_id}/reconcile")
def reconcile_credit_note_alias(
    credit_note_id: str,
    actor: str = Query("CREDIT_AUDITOR"),
    db: Session = Depends(get_db)
):
    """Alias for validating and reconciling credit notes."""
    return validate_credit_note(
        credit_note_id=credit_note_id,
        req=CreditNoteValidateRequest(actor=actor),
        db=db
    )
