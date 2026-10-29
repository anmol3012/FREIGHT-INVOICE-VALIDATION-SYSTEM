"""
Audit Detection Evaluator & Accuracy Benchmarking Service.
Compares operational validation decisions and detected exceptions against
independently stored ground-truth anomaly labels.
Computes Confusion Matrix, Precision, Recall, F1, and financial recovery metrics.
"""

from typing import Dict, Any, List
from sqlalchemy.orm import Session

from backend.app.models.invoice import FreightInvoice
from backend.app.models.ground_truth import GroundTruthLabel
from backend.app.models.audit_exception import AuditException
from backend.app.models.credit_note import CreditNote
from backend.app.models.enums import (
    InvoiceStatus, ValidationStatus, ExceptionStatus,
    CreditNoteApprovalStatus, CreditNoteReconciliationStatus
)


class AuditEvaluator:
    """
    Evaluates Validation Engine Detection Performance against independently stored Ground-Truth labels.
    Calculates exact classification metrics, financial recovery, and negative scenario breakdowns.
    """

    @classmethod
    def evaluate(cls, db: Session) -> Dict[str, Any]:
        # 1. Fetch ground truth labels
        labels = db.query(GroundTruthLabel).all()
        if not labels:
            return {"error": "No ground truth labels found in evaluation store"}

        gt_by_invoice = {lbl.invoice_id: lbl for lbl in labels}

        # 2. Fetch all operational invoices
        invoices = db.query(FreightInvoice).all()
        inv_by_id = {inv.invoice_id: inv for inv in invoices}

        # Counters for Invoice-level Confusion Matrix
        tp = 0 # Ground truth = Anomaly (FAIL), Engine = Failed/Disputed
        fp = 0 # Ground truth = Clean (PASS), Engine = Failed/Disputed
        tn = 0 # Ground truth = Clean (PASS), Engine = Passed (Match)
        fn = 0 # Ground truth = Anomaly (FAIL), Engine = Passed (Match)

        scenario_breakdown: Dict[str, Dict[str, int]] = {}
        total_injected_variance = 0.0
        total_detected_variance = 0.0

        for inv_id, gt in gt_by_invoice.items():
            inv = inv_by_id.get(inv_id)
            if not inv:
                continue

            expected_fail = (gt.expected_decision == "FAIL" or gt.is_anomaly)
            actual_fail = (
                inv.validation_status == ValidationStatus.FAILED or
                inv.invoice_status in [InvoiceStatus.EXCEPTION_DISPUTED, InvoiceStatus.REJECTED] or
                len(inv.audit_exceptions) > 0
            )

            scen = gt.issue_type
            if scen not in scenario_breakdown:
                scenario_breakdown[scen] = {
                    "total_injected": 0,
                    "detected": 0,
                    "missed": 0,
                    "false_alarms": 0,
                    "injected_variance": 0.0,
                    "detected_variance": 0.0
                }

            scenario_breakdown[scen]["total_injected"] += 1
            if expected_fail:
                scenario_breakdown[scen]["injected_variance"] += round(gt.injected_variance, 2)
                total_injected_variance += round(gt.injected_variance, 2)

            if expected_fail and actual_fail:
                tp += 1
                scenario_breakdown[scen]["detected"] += 1
                det_var = round(inv.variance_amount, 2)
                scenario_breakdown[scen]["detected_variance"] += det_var
                total_detected_variance += det_var
            elif not expected_fail and actual_fail:
                fp += 1
                scenario_breakdown[scen]["false_alarms"] += 1
            elif not expected_fail and not actual_fail:
                tn += 1
            elif expected_fail and not actual_fail:
                fn += 1
                scenario_breakdown[scen]["missed"] += 1

        total_audited = tp + fp + tn + fn

        # Safe Metric Calculations (explicit zero-denominator handling)
        accuracy = round((tp + tn) / max(1, total_audited), 4) if total_audited > 0 else 0.0
        precision = round(tp / max(1, tp + fp), 4) if (tp + fp) > 0 else 0.0
        recall = round(tp / max(1, tp + fn), 4) if (tp + fn) > 0 else 0.0
        specificity = round(tn / max(1, tn + fp), 4) if (tn + fp) > 0 else 0.0
        f1_score = round(2 * (precision * recall) / max(1e-6, precision + recall), 4) if (precision + recall) > 0 else 0.0

        # Exceptions & Duplicates Metrics
        exceptions = db.query(AuditException).all()
        total_exceptions = len(exceptions)
        unresolved_exceptions = sum(
            1 for e in exceptions
            if e.exception_status in [ExceptionStatus.OPEN, ExceptionStatus.UNDER_REVIEW, ExceptionStatus.DISPUTED]
        )
        duplicate_invoices_count = sum(
            1 for e in exceptions if e.exception_type.value == "DUPLICATE_BILLING" and e.invoice_line_id is None
        )
        duplicate_surcharge_count = sum(
            1 for e in exceptions if e.exception_type.value == "DUPLICATE_BILLING" and e.invoice_line_id is not None
        )
        data_integrity_failures = sum(
            1 for e in exceptions if e.exception_type.value in ["UNMATCHED_SHIPMENT", "CALCULATION_ERROR"]
        )

        # Invoice Status Counts
        valid_invoices_count = sum(1 for inv in invoices if inv.validation_status == ValidationStatus.PASSED)
        disputed_invoices_count = sum(1 for inv in invoices if inv.invoice_status == InvoiceStatus.EXCEPTION_DISPUTED)
        rejected_invoices_count = sum(1 for inv in invoices if inv.invoice_status == InvoiceStatus.REJECTED)

        # Credit Note Financials
        credit_notes = db.query(CreditNote).all()
        total_approved_credit = round(sum(
            cn.credit_amount for cn in credit_notes
            if cn.approval_status == CreditNoteApprovalStatus.APPROVED
        ), 2)
        total_reconciled_credit = round(sum(
            cn.credit_amount for cn in credit_notes
            if cn.reconciliation_status in [CreditNoteReconciliationStatus.FULLY_APPLIED, CreditNoteReconciliationStatus.PARTIALLY_APPLIED]
        ), 2)
        total_rejected_credit = round(sum(
            cn.credit_amount for cn in credit_notes
            if cn.approval_status == CreditNoteApprovalStatus.REJECTED or cn.reconciliation_status == CreditNoteReconciliationStatus.REJECTED
        ), 2)

        recovery_rate = round((total_detected_variance / max(1e-6, total_injected_variance)) * 100.0, 1) if total_injected_variance > 0 else 0.0

        # Scenario breakdown formatting
        scenario_results = {}
        for scen, counts in scenario_breakdown.items():
            tot = counts["total_injected"]
            det = counts["detected"]
            rate = round((det / max(1, tot)) * 100.0, 1) if scen != "NORMAL" else round(((tot - counts["false_alarms"]) / max(1, tot)) * 100.0, 1)
            scenario_results[scen] = {
                "total_injected": tot,
                "detected": det,
                "missed": counts["missed"],
                "false_alarms": counts["false_alarms"],
                "detection_rate_pct": rate,
                "injected_variance": round(counts["injected_variance"], 2),
                "detected_variance": round(counts["detected_variance"], 2)
            }

        return {
            "summary": {
                "total_invoices_processed": total_audited,
                "valid_invoices": valid_invoices_count,
                "invoices_requiring_review": disputed_invoices_count,
                "rejected_invoices": rejected_invoices_count,
                "total_detected_exceptions": total_exceptions,
                "unresolved_exceptions": unresolved_exceptions,
                "duplicate_invoices_detected": duplicate_invoices_count,
                "duplicate_surcharges_detected": duplicate_surcharge_count,
                "data_integrity_failures": data_integrity_failures,
                "true_positives": tp,
                "false_positives": fp,
                "true_negatives": tn,
                "false_negatives": fn,
            },
            "metrics": {
                "accuracy": accuracy,
                "precision": precision,
                "recall": recall,
                "specificity": specificity,
                "f1_score": f1_score,
            },
            "financial_impact": {
                "total_injected_overbilling_usd": round(total_injected_variance, 2),
                "total_detected_overbilling_usd": round(total_detected_variance, 2),
                "recovery_rate_pct": recovery_rate,
                "total_approved_credit_usd": total_approved_credit,
                "total_reconciled_credit_usd": total_reconciled_credit,
                "total_rejected_credit_usd": total_rejected_credit
            },
            "scenario_breakdown": scenario_results
        }
