from typing import List, Optional, Dict, Any
from pydantic import BaseModel, ConfigDict
from datetime import date, datetime

class CarrierOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    carrier_code: str
    name: str
    tax_id: str
    payment_terms_days: int
    status: str
    contact_email: Optional[str] = None

class InvoiceLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    line_number: int
    charge_type: str
    charge_code: Optional[str] = None
    description: str
    billed_units: float
    billed_rate: float
    billed_amount: float
    expected_units: float
    expected_rate: float
    expected_amount: float
    variance_amount: float
    status: str
    discrepancy_reason: Optional[str] = None

class InvoiceExceptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    invoice_id: int
    invoice_line_id: Optional[int] = None
    category: str
    severity: str
    billed_amount: float
    expected_amount: float
    variance_amount: float
    status: str
    root_cause_code: str
    explanation: str
    resolved_by: Optional[str] = None
    resolution_notes: Optional[str] = None
    created_at: datetime
    resolved_at: Optional[datetime] = None

class InvoiceHeaderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    invoice_number: str
    carrier_id: int
    carrier_code: Optional[str] = None
    carrier_name: Optional[str] = None
    shipment_id: Optional[int] = None
    bol_number_billed: str
    invoice_date: date
    due_date: date
    currency: str
    total_billed_amount: float
    calculated_expected_amount: float
    total_variance_amount: float
    status: str
    validation_status: str
    is_duplicate: bool
    duplicate_of_invoice_id: Optional[int] = None
    reconciliation_notes: Optional[str] = None
    created_at: datetime
    validated_at: Optional[datetime] = None
    lines: List[InvoiceLineOut] = []
    exceptions: List[InvoiceExceptionOut] = []

class CreditNoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    credit_note_number: str
    carrier_id: int
    original_invoice_id: int
    original_invoice_number: Optional[str] = None
    issue_date: date
    credit_amount: float
    applied_amount: float
    remaining_balance: float
    status: str
    reason_code: str
    rejection_reason: Optional[str] = None

class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    entity_type: str
    entity_id: str
    event_type: str
    actor: str
    payload_json: Optional[str] = None
    notes: Optional[str] = None
    timestamp: datetime

class DashboardKPIs(BaseModel):
    total_invoices: int
    validated_match_count: int
    exception_disputed_count: int
    paid_count: int
    match_rate_pct: float
    total_billed_usd: float
    total_expected_usd: float
    total_variance_recovered_usd: float
    exceptions_by_category: Dict[str, int]
    invoices_by_status: Dict[str, int]
