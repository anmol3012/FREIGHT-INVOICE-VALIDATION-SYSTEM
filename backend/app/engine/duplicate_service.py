"""
Duplicate Detection Service for Freight Invoice Validation System.
Detects exact duplicate invoice numbers, repeated billing of the same shipment,
duplicate lines (e.g. secondary fuel surcharge), and manages duplicate clusters.
"""

import hashlib
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session

from backend.app.models.invoice import FreightInvoice, InvoiceLine, DuplicateInvoiceGroup
from backend.app.models.enums import InvoiceLineType, InvoiceStatus


@dataclass
class DuplicateCheckResult:
    is_duplicate: bool
    duplicate_type: Optional[str] = None # "EXACT_INVOICE_NUMBER", "REPEATED_SHIPMENT_BILLING", "DUPLICATE_FINGERPRINT", "DUPLICATE_LINE_ITEM"
    severity: str = "CRITICAL"
    canonical_invoice_id: Optional[str] = None
    canonical_invoice_number: Optional[str] = None
    duplicate_group_id: Optional[str] = None
    fingerprint_hash: Optional[str] = None
    explanation: Optional[str] = None
    duplicate_lines: List[Dict[str, Any]] = field(default_factory=list)


class DuplicateDetectionService:
    """
    Multi-level duplicate billing detection engine.
    """

    @staticmethod
    def compute_fingerprint(carrier_id: str, shipment_ref: str, total_billed: float) -> str:
        raw = f"{carrier_id.strip()}:{shipment_ref.strip().upper()}:{total_billed:.2f}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @classmethod
    def check_invoice_duplicate(
        cls, db: Session, invoice: FreightInvoice
    ) -> DuplicateCheckResult:
        # 1. Check if same invoice number already exists for this carrier (excluding this record)
        existing_num = db.query(FreightInvoice).filter(
            FreightInvoice.carrier_id == invoice.carrier_id,
            FreightInvoice.invoice_number == invoice.invoice_number,
            FreightInvoice.invoice_id != invoice.invoice_id
        ).first()

        if existing_num:
            return DuplicateCheckResult(
                is_duplicate=True,
                duplicate_type="EXACT_INVOICE_NUMBER",
                severity="CRITICAL",
                canonical_invoice_id=existing_num.invoice_id,
                canonical_invoice_number=existing_num.invoice_number,
                duplicate_group_id=existing_num.duplicate_group_id,
                explanation=f"Exact duplicate invoice number '{invoice.invoice_number}' already registered by carrier {invoice.carrier_id} on invoice {existing_num.invoice_id}."
            )

        # 2. Check fingerprint hash matching an earlier invoice
        fp = invoice.fingerprint_hash or cls.compute_fingerprint(
            invoice.carrier_id, invoice.raw_shipment_reference, invoice.billed_total
        )

        fp_match = db.query(FreightInvoice).filter(
            FreightInvoice.carrier_id == invoice.carrier_id,
            FreightInvoice.fingerprint_hash == fp,
            FreightInvoice.invoice_id != invoice.invoice_id,
            FreightInvoice.created_at <= invoice.created_at
        ).order_by(FreightInvoice.created_at.asc()).first()

        if fp_match:
            return DuplicateCheckResult(
                is_duplicate=True,
                duplicate_type="DUPLICATE_FINGERPRINT",
                severity="CRITICAL",
                canonical_invoice_id=fp_match.invoice_id,
                canonical_invoice_number=fp_match.invoice_number,
                duplicate_group_id=fp_match.duplicate_group_id,
                fingerprint_hash=fp,
                explanation=f"Duplicate billing cluster: identical carrier, shipment ref '{invoice.raw_shipment_reference}', and amount ${invoice.billed_total:.2f} already billed on invoice {fp_match.invoice_number}."
            )

        # 3. Check repeat billing of the same shipment reference if previously validated or paid
        if invoice.raw_shipment_reference:
            repeat_shipment = db.query(FreightInvoice).filter(
                FreightInvoice.carrier_id == invoice.carrier_id,
                FreightInvoice.raw_shipment_reference == invoice.raw_shipment_reference,
                FreightInvoice.invoice_id != invoice.invoice_id,
                FreightInvoice.invoice_status.in_([
                    InvoiceStatus.VALIDATED_MATCH,
                    InvoiceStatus.PAID,
                    InvoiceStatus.SUBMITTED
                ])
            ).order_by(FreightInvoice.created_at.asc()).first()

            if repeat_shipment and repeat_shipment.invoice_id != invoice.invoice_id:
                return DuplicateCheckResult(
                    is_duplicate=True,
                    duplicate_type="REPEATED_SHIPMENT_BILLING",
                    severity="CRITICAL",
                    canonical_invoice_id=repeat_shipment.invoice_id,
                    canonical_invoice_number=repeat_shipment.invoice_number,
                    duplicate_group_id=repeat_shipment.duplicate_group_id,
                    explanation=f"Shipment '{invoice.raw_shipment_reference}' was already billed on invoice {repeat_shipment.invoice_number} (Status: {repeat_shipment.invoice_status.value})."
                )

        return DuplicateCheckResult(is_duplicate=False)

    @classmethod
    def check_duplicate_lines(
        cls, lines: List[InvoiceLine]
    ) -> List[Dict[str, Any]]:
        """
        Detects duplicate charges within the invoice itself (e.g. Scenario D: Duplicate Fuel Surcharge).
        """
        duplicates = []
        fsc_lines = []
        seen_linehauls = []
        seen_accessorial_codes = set()

        for line in lines:
            # Check fuel surcharge
            l_type = line.line_type.value if hasattr(line.line_type, "value") else str(line.line_type)
            if l_type == "FUEL_SURCHARGE" or "FUEL" in (line.description or "").upper():
                fsc_lines.append(line)

            # Check linehaul
            elif l_type == "BASE_LINEHAUL":
                seen_linehauls.append(line)

        # If more than 1 Fuel Surcharge line exists, the subsequent ones are duplicates
        if len(fsc_lines) > 1:
            for extra_fsc in fsc_lines[1:]:
                duplicates.append({
                    "line_id": extra_fsc.invoice_line_id,
                    "line_number": extra_fsc.line_number,
                    "charge_type": "FUEL_SURCHARGE",
                    "duplicate_type": "DUPLICATE_FUEL_SURCHARGE",
                    "billed_amount": extra_fsc.billed_amount,
                    "explanation": f"Duplicate fuel surcharge line {extra_fsc.line_number} assessed (${extra_fsc.billed_amount:.2f}). Contract permits only one primary fuel surcharge per shipment."
                })

        # If more than 1 base linehaul line exists
        if len(seen_linehauls) > 1:
            for extra_lh in seen_linehauls[1:]:
                duplicates.append({
                    "line_id": extra_lh.invoice_line_id,
                    "line_number": extra_lh.line_number,
                    "charge_type": "BASE_LINEHAUL",
                    "duplicate_type": "DUPLICATE_LINEHAUL",
                    "billed_amount": extra_lh.billed_amount,
                    "explanation": f"Multiple base linehaul lines billed on line {extra_lh.line_number} (${extra_lh.billed_amount:.2f})."
                })

        return duplicates
