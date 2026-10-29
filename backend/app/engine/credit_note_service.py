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
from backend.app.engine.audit_service import AuditService


@dataclass
class CreditNoteValidationResult:
    credit_note_id: str
    credit_note_number: str
    is_valid: bool
    approval_status: CreditNoteApprovalStatus
    reconciliation_status: CreditNoteReconciliationStatus
    credit_amount: float
    approved_disputed_balance: float
    remaining_balance_after_credit: float
    excess_amount: float
    explanation: str


class CreditNoteService:
    """
    Validates and reconciles carrier credit notes against disputed audit exceptions.
    Ensures that invalid or excessive credit notes do not reduce the outstanding dispute balance.
    """

    @classmethod
    def calculate_remaining_balance(cls, db: Session, exception: AuditException) -> float:
        """
        remaining_creditable_balance = approved_disputed_amount - total_previously_accepted_credits
        """
        disputed_limit = round(exception.disputed_amount, 2)
        approved_credits = db.query(CreditNote).filter(
            CreditNote.exception_id == exception.exception_id,
            CreditNote.approval_status == CreditNoteApprovalStatus.APPROVED,
            CreditNote.reconciliation_status.in_([
                CreditNoteReconciliationStatus.FULLY_APPLIED,
                CreditNoteReconciliationStatus.PARTIALLY_APPLIED
            ])
        ).all()
        already_credited = sum(round(c.credit_amount, 2) for c in approved_credits)
        return max(0.0, round(disputed_limit - already_credited, 2))

    @classmethod
    def validate_credit_note(
        cls,
        db: Session,
        credit_note_id: str,
        actor: str = "CREDIT_AUDITOR"
    ) -> CreditNoteValidationResult:
        cn = db.query(CreditNote).filter(CreditNote.credit_note_id == credit_note_id).first()
        if not cn:
            raise ValueError(f"Credit note '{credit_note_id}' not found.")

        # Check if already reconciled
        if cn.reconciliation_status in [CreditNoteReconciliationStatus.FULLY_APPLIED, CreditNoteReconciliationStatus.PARTIALLY_APPLIED]:
            return CreditNoteValidationResult(
                credit_note_id=cn.credit_note_id,
                credit_note_number=cn.credit_note_number,
                is_valid=True,
                approval_status=cn.approval_status,
                reconciliation_status=cn.reconciliation_status,
                credit_amount=cn.credit_amount,
                approved_disputed_balance=0.0,
                remaining_balance_after_credit=0.0,
                excess_amount=0.0,
                explanation=f"Credit note {cn.credit_note_number} is already reconciled ({cn.reconciliation_status.value})."
            )

        if cn.approval_status == CreditNoteApprovalStatus.REJECTED:
            return CreditNoteValidationResult(
                credit_note_id=cn.credit_note_id,
                credit_note_number=cn.credit_note_number,
                is_valid=False,
                approval_status=cn.approval_status,
                reconciliation_status=cn.reconciliation_status,
                credit_amount=cn.credit_amount,
                approved_disputed_balance=0.0,
                remaining_balance_after_credit=0.0,
                excess_amount=0.0,
                explanation=f"Credit note {cn.credit_note_number} was previously rejected."
            )

        # 1. Check positive amount
        if cn.credit_amount <= 0:
            cn.approval_status = CreditNoteApprovalStatus.REJECTED
            cn.reconciliation_status = CreditNoteReconciliationStatus.REJECTED
            AuditService.transition_credit_note(
                db=db,
                credit_note=cn,
                target_reconciliation_status=CreditNoteReconciliationStatus.REJECTED,
                reason=f"Credit note amount must be strictly positive (Billed: ${cn.credit_amount:.2f}).",
                actor=actor
            )
            return CreditNoteValidationResult(
                credit_note_id=cn.credit_note_id,
                credit_note_number=cn.credit_note_number,
                is_valid=False,
                approval_status=cn.approval_status,
                reconciliation_status=cn.reconciliation_status,
                credit_amount=cn.credit_amount,
                approved_disputed_balance=0.0,
                remaining_balance_after_credit=0.0,
                excess_amount=0.0,
                explanation=f"Credit note {cn.credit_note_number} rejected: Credit amount must be strictly positive."
            )

        # 2. Check for duplicate credit note submission
        duplicate_cn = db.query(CreditNote).filter(
            CreditNote.carrier_id == cn.carrier_id,
            CreditNote.credit_note_number == cn.credit_note_number,
            CreditNote.credit_note_id != cn.credit_note_id
        ).first()

        if duplicate_cn:
            cn.approval_status = CreditNoteApprovalStatus.REJECTED
            cn.reconciliation_status = CreditNoteReconciliationStatus.REJECTED
            AuditService.transition_credit_note(
                db=db,
                credit_note=cn,
                target_reconciliation_status=CreditNoteReconciliationStatus.REJECTED,
                reason=f"Duplicate credit note number '{cn.credit_note_number}' already submitted on record {duplicate_cn.credit_note_id}.",
                actor=actor
            )
            return CreditNoteValidationResult(
                credit_note_id=cn.credit_note_id,
                credit_note_number=cn.credit_note_number,
                is_valid=False,
                approval_status=cn.approval_status,
                reconciliation_status=cn.reconciliation_status,
                credit_amount=cn.credit_amount,
                approved_disputed_balance=0.0,
                remaining_balance_after_credit=0.0,
                excess_amount=0.0,
                explanation=f"Credit note {cn.credit_note_number} rejected: Duplicate submission detected."
            )

        # 3. Check linked exception & invoice
        exception = None
        if cn.exception_id:
            exception = db.query(AuditException).filter(
                AuditException.exception_id == cn.exception_id
            ).first()

        if not exception and cn.invoice_id:
            exception = db.query(AuditException).filter(
                AuditException.invoice_id == cn.invoice_id
            ).first()

        if not exception:
            cn.approval_status = CreditNoteApprovalStatus.REJECTED
            cn.reconciliation_status = CreditNoteReconciliationStatus.REJECTED
            AuditService.transition_credit_note(
                db=db,
                credit_note=cn,
                target_reconciliation_status=CreditNoteReconciliationStatus.REJECTED,
                reason="No matching open audit exception found for this credit note.",
                actor=actor
            )
            return CreditNoteValidationResult(
                credit_note_id=cn.credit_note_id,
                credit_note_number=cn.credit_note_number,
                is_valid=False,
                approval_status=cn.approval_status,
                reconciliation_status=cn.reconciliation_status,
                credit_amount=cn.credit_amount,
                approved_disputed_balance=0.0,
                remaining_balance_after_credit=0.0,
                excess_amount=cn.credit_amount,
                explanation=f"Credit note {cn.credit_note_number} rejected: No corresponding open audit dispute found for invoice {cn.invoice_id}."
            )

        # 4. Check currency compatibility
        if cn.currency and exception.currency and cn.currency.upper() != exception.currency.upper():
            cn.approval_status = CreditNoteApprovalStatus.REJECTED
            cn.reconciliation_status = CreditNoteReconciliationStatus.REJECTED
            AuditService.transition_credit_note(
                db=db,
                credit_note=cn,
                target_reconciliation_status=CreditNoteReconciliationStatus.REJECTED,
                reason=f"Currency mismatch: Credit note currency '{cn.currency}' does not match dispute currency '{exception.currency}'.",
                actor=actor
            )
            return CreditNoteValidationResult(
                credit_note_id=cn.credit_note_id,
                credit_note_number=cn.credit_note_number,
                is_valid=False,
                approval_status=cn.approval_status,
                reconciliation_status=cn.reconciliation_status,
                credit_amount=cn.credit_amount,
                approved_disputed_balance=exception.disputed_amount,
                remaining_balance_after_credit=exception.disputed_amount,
                excess_amount=0.0,
                explanation=f"Credit note {cn.credit_note_number} rejected: Currency mismatch ({cn.currency} vs {exception.currency})."
            )

        # 5. Check remaining balance limit (Scenario E: Excessive Credit Note Check)
        remaining_balance = cls.calculate_remaining_balance(db, exception)

        if cn.credit_amount > remaining_balance + 0.05: # tolerance
            excess = round(cn.credit_amount - remaining_balance, 2)
            cn.approval_status = CreditNoteApprovalStatus.REJECTED
            cn.reconciliation_status = CreditNoteReconciliationStatus.REJECTED
            AuditService.transition_credit_note(
                db=db,
                credit_note=cn,
                target_reconciliation_status=CreditNoteReconciliationStatus.REJECTED,
                reason=f"Scenario E Violation: Credit note amount (${cn.credit_amount:.2f}) exceeds remaining approved dispute balance (${remaining_balance:.2f}) by ${excess:.2f}.",
                actor=actor
            )
            return CreditNoteValidationResult(
                credit_note_id=cn.credit_note_id,
                credit_note_number=cn.credit_note_number,
                is_valid=False,
                approval_status=cn.approval_status,
                reconciliation_status=cn.reconciliation_status,
                credit_amount=cn.credit_amount,
                approved_disputed_balance=remaining_balance,
                remaining_balance_after_credit=remaining_balance, # Balance unchanged!
                excess_amount=excess,
                explanation=f"Scenario E Violation: Credit note {cn.credit_note_number} amount (${cn.credit_amount:.2f}) exceeds approved disputed balance (${remaining_balance:.2f}) by ${excess:.2f}."
            )

        # 6. Approved credit note
        cn.approval_status = CreditNoteApprovalStatus.APPROVED
        new_balance = round(remaining_balance - cn.credit_amount, 2)

        if new_balance <= 0.05:
            target_recon = CreditNoteReconciliationStatus.FULLY_APPLIED
            AuditService.transition_exception(
                db=db,
                exception=exception,
                target_status=ExceptionStatus.AUTO_RESOLVED,
                reason=f"Dispute fully resolved by credit note {cn.credit_note_number} (${cn.credit_amount:.2f}).",
                actor=actor
            )
        else:
            target_recon = CreditNoteReconciliationStatus.PARTIALLY_APPLIED

        AuditService.transition_credit_note(
            db=db,
            credit_note=cn,
            target_reconciliation_status=target_recon,
            reason=f"Credit note accepted against dispute. Remaining balance: ${new_balance:.2f}.",
            actor=actor
        )

        db.flush()
        return CreditNoteValidationResult(
            credit_note_id=cn.credit_note_id,
            credit_note_number=cn.credit_note_number,
            is_valid=True,
            approval_status=cn.approval_status,
            reconciliation_status=cn.reconciliation_status,
            credit_amount=cn.credit_amount,
            approved_disputed_balance=remaining_balance,
            remaining_balance_after_credit=new_balance,
            excess_amount=0.0,
            explanation=f"Credit note {cn.credit_note_number} approved and reconciled (${cn.credit_amount:.2f} against ${remaining_balance:.2f} balance)."
        )
