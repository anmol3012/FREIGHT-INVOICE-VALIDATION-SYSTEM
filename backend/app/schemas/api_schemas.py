"""
Pydantic API Schemas for Freight Invoice Validation System (Phase 5).
Maps full relational data models and business workflows to REST API responses and requests.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, ConfigDict
from datetime import date, datetime


class CarrierOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    carrier_id: str
    carrier_code: str
    carrier_name: str
    status: str
    country_code: str
    created_at: datetime


class InvoiceLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    invoice_line_id: str
    invoice_id: str
    line_number: int
    line_type: str
    accessorial_id: Optional[str] = None
    description: str
    quantity: float
    unit_of_measure: str
    unit_rate: float
    billed_amount: float
    expected_amount: float
    variance_amount: float
    evidence_reference: Optional[str] = None
    source_reference: Optional[str] = None
    created_at: datetime


class AuditExceptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    exception_id: str
    invoice_id: str
    invoice_line_id: Optional[str] = None
    shipment_id: Optional[str] = None
    exception_type: str
    severity: str
    expected_amount: float
    billed_amount: float
    disputed_amount: float
    currency: str
    explanation: str
    evidence_json: Optional[str] = None
    exception_status: str
    detected_at: datetime
    resolved_at: Optional[datetime] = None


class CreditNoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    credit_note_id: str
    credit_note_number: str
    carrier_id: str
    invoice_id: str
    exception_id: Optional[str] = None
    issue_date: date
    currency: str
    credit_amount: float
    approval_status: str
    reconciliation_status: str
    created_at: datetime


class FreightInvoiceSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    invoice_id: str
    carrier_id: str
    carrier_code: Optional[str] = None
    carrier_name: Optional[str] = None
    shipment_id: Optional[str] = None
    raw_shipment_reference: str
    invoice_number: str
    invoice_date: date
    service_period_start: date
    service_period_end: date
    due_date: date
    currency: str
    billed_total: float
    expected_total: float
    variance_amount: float
    invoice_status: str
    validation_status: str
    duplicate_group_id: Optional[str] = None
    fingerprint_hash: Optional[str] = None
    exception_count: int = 0
    created_at: datetime


class FreightInvoiceDetailOut(FreightInvoiceSummaryOut):
    lines: List[InvoiceLineOut] = []
    exceptions: List[AuditExceptionOut] = []
    credit_notes: List[CreditNoteOut] = []


class PaginatedInvoicesOut(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[FreightInvoiceSummaryOut]


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: str
    entity_type: str
    entity_id: str
    event_type: str
    actor: str
    notes: Optional[str] = None
    timestamp: datetime
    payload_json: Optional[str] = None


class DashboardKPIs(BaseModel):
    total_invoices: int
    validated_match_count: int
    exception_disputed_count: int
    pending_audit_count: int
    paid_count: int
    rejected_count: int
    match_rate_pct: float
    total_billed_usd: float
    total_expected_usd: float
    total_variance_recovered_usd: float
    exceptions_by_category: Dict[str, int]
    invoices_by_status: Dict[str, int]
    top_carriers: List[Dict[str, Any]] = []


class ValidationTriggerResponse(BaseModel):
    invoice_id: str
    overall_verdict: str
    validation_status: str
    invoice_status: str
    billed_total: float
    expected_total: float
    variance_amount: float
    exceptions_raised_count: int
    exception_ids: List[str]
    diagnostic_messages: List[str]


class ExceptionStatusUpdateRequest(BaseModel):
    target_status: str
    reason: str
    actor: str = "AUDIT_OFFICER"


class ManualOverrideRequest(BaseModel):
    approved_amount: float
    reason: str
    actor: str = "COMPLIANCE_LEAD"


class CreditNoteValidateRequest(BaseModel):
    actor: str = "CREDIT_AUDITOR"


class TraceabilityResponse(BaseModel):
    invoice_id: str
    invoice_number: str
    carrier: Optional[Dict[str, Any]] = None
    shipment: Optional[Dict[str, Any]] = None
    rate_card: Optional[Dict[str, Any]] = None
    weight_measurements: List[Dict[str, Any]] = []
    delivery_evidence: Optional[Dict[str, Any]] = None
    invoice_lines: List[Dict[str, Any]] = []
    exceptions: List[Dict[str, Any]] = []
    credit_notes: List[Dict[str, Any]] = []
    status_history: List[Dict[str, Any]] = []
    audit_events: List[Dict[str, Any]] = []


class EvaluationReportOut(BaseModel):
    evaluated_at: datetime
    summary: Dict[str, Any]
    metrics: Dict[str, Any]
    financial_impact: Dict[str, Any]
    scenario_breakdown: Dict[str, Any]


class HealthCheckResponse(BaseModel):
    status: str
    database: str
    timestamp: datetime


class ReadinessResponse(BaseModel):
    ready: bool
    tables_initialized: bool
    total_invoices: int


class DatasetGenerateRequest(BaseModel):
    scale: str = "starter"
    seed: int = 20261022
    reset: bool = False


class DatasetGenerateResponse(BaseModel):
    status: str
    scale: str
    seed: int
    counts: Dict[str, int]


class BatchValidationRequest(BaseModel):
    invoice_ids: Optional[List[str]] = None
    actor: str = "BATCH_AUDITOR"


class BatchValidationResponse(BaseModel):
    total_audited: int
    passed_count: int
    failed_count: int
    total_variance_recovered_usd: float
    duration_seconds: float


class RateCardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rate_card_id: str
    carrier_id: str
    lane_id: str
    service_level: str
    currency: str
    effective_from: date
    effective_to: Optional[date] = None
    base_rate: float
    minimum_charge: float
    status: str
    tier_count: int = 0


class LaneOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    lane_id: str
    origin_location_code: str
    destination_location_code: str
    origin_city: str
    destination_city: str
    origin_country: str
    destination_country: str
    distance_km: float
    status: str


class ShipmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    shipment_id: str
    carrier_id: str
    lane_id: str
    service_level: str
    ship_date: date
    delivery_due_date: date
    actual_length_cm: float
    actual_width_cm: float
    actual_height_cm: float
    actual_weight_kg: float
    chargeable_weight_kg: float
    currency: str
    shipment_status: str
