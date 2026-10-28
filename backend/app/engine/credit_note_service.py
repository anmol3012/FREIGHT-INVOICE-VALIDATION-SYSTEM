"""
Credit Note Validation & Reconciliation Service for Freight Invoice Validation System.
Validates credit notes against approved exception disputed balances,
enforcing Scenario E protection against excessive or invalid credit issuance.
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session

from backend.app.models.credit_note import CreditNote
from backend.app.models.audit_exception import AuditException
from backend.app.models.invoice import FreightInvoice
from backend.app.models.enums import (
    CreditNoteApprovalStatus, CreditNoteReconciliationStatus, ExceptionStatus
)


@dataclass
class CreditNoteValidationResult:
    credit_note_id: str
    credit_note_number: str
    is_valid: bool
    approval_status: CreditNoteApprovalStatus
    reconciliation_status: CreditNoteReconciliationStatus
    credit_amount: float
    approved_disputed_balance: float
    excess_amount: float
    explanation: str


class CreditNoteService:
    """
    Validates and reconciles carrier credit notes against disputed audit exceptions.
    """

    @classmethod
    def validate_credit_note(
        cls, db: Session, credit_note_id: str
    ) -> CreditNoteValidationResult:
        cn = db.query(CreditNote).filter(CreditNote.credit_note_id == credit_note_id).first()
        if not cn:
            raise ValueError(f"Credit note '{credit_note_id}' not found.")

        # Check linked exception
        exception = None
        if cn.exception_id:
            exception = db.query(AuditException).filter(
                AuditException.exception_id == cn.exception_id
            ).first()

        # If no explicit exception_id, check if invoice has an active exception
        if not exception and cn.invoice_id:
            exception = db.query(AuditException).filter(
                AuditException.invoice_id == cn.invoice_id
            ).first()

        if not exception:
            # Unlinked credit note or invoice has no registered dispute
            cn.approval_status = CreditNoteApprovalStatus.REJECTED
            cn.reconciliation_status = CreditNoteReconciliationStatus.REJECTED
            db.flush()
            return CreditNoteValidationResult(
                credit_note_id=cn.credit_note_id,
                credit_note_number=cn.credit_note_number,
                is_valid=False,
                approval_status=cn.approval_status,
                reconciliation_status=cn.reconciliation_status,
                credit_amount=cn.credit_amount,
                approved_disputed_balance=0.0,
                excess_amount=cn.credit_amount,
                explanation=f"Credit note {cn.credit_note_number} rejected: No corresponding open audit dispute exception found for invoice {cn.invoice_id}."
            )

        # Calculate already approved/applied credits on this exception
        existing_credits = db.query(CreditNote).filter(
            CreditNote.exception_id == exception.exception_id,
            CreditNote.credit_note_id != cn.credit_note_id,
            CreditNote.approval_status == CreditNoteApprovalStatus.APPROVED
        ).all()
        already_credited = sum(c.credit_amount for c in existing_credits)

        disputed_limit = round(exception.disputed_amount, 2)
        remaining_balance = max(0.0, round(disputed_limit - already_credited, 2))

        # Scenario E Check: Credit Note Exceeding Approved Disputed Amount
        if cn.credit_amount > remaining_balance + 0.05: # tolerance
            excess = round(cn.credit_amount - remaining_balance, 2)
            cn.approval_status = CreditNoteApprovalStatus.REJECTED
            cn.reconciliation_status = CreditNoteReconciliationStatus.REJECTED
            db.flush()
            return CreditNoteValidationResult(
                credit_note_id=cn.credit_note_id,
                credit_note_number=cn.credit_note_number,
                is_valid=False,
                approval_status=cn.approval_status,
                reconciliation_status=cn.reconciliation_status,
                credit_amount=cn.credit_amount,
                approved_disputed_balance=remaining_balance,
                excess_amount=excess,
                explanation=f"Scenario E Violation: Credit note {cn.credit_note_number} amount (${cn.credit_amount:.2f}) exceeds approved disputed balance (${remaining_balance:.2f}) by ${excess:.2f}."
            )

        # Valid credit note within approved limits
        cn.approval_status = CreditNoteApprovalStatus.APPROVED
        if abs(cn.credit_amount - remaining_balance) <= 0.05:
            cn.reconciliation_status = CreditNoteReconciliationStatus.FULLY_APPLIED
            exception.exception_status = ExceptionStatus.AUTO_RESOLVED
        else:
            cn.reconciliation_status = CreditNoteReconciliationStatus.PARTIALLY_APPLIED

        db.flush()
        return CreditNoteValidationResult(
            credit_note_id=cn.credit_note_id,
            credit_note_number=cn.credit_note_number,
            is_valid=True,
            approval_status=cn.approval_status,
            reconciliation_status=cn.reconciliation_status,
            credit_amount=cn.credit_amount,
            approved_disputed_balance=remaining_balance,
            excess_amount=0.0,
            explanation=f"Credit note {cn.credit_note_number} approved and reconciled (${cn.credit_amount:.2f} against ${remaining_balance:.2f} dispute)."
        )
