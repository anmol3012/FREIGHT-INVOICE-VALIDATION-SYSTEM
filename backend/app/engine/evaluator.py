from typing import Dict, List, Any
from sqlalchemy.orm import Session
from backend.app.models.invoice import InvoiceHeader
from backend.app.models.ground_truth import GroundTruthLabel
from backend.app.models.exception import InvoiceException
from backend.app.models.credit_note import CreditNote

class AuditEvaluator:
    """
    Evaluates Validation Engine Detection Performance against
    independently stored Ground-Truth labels.
    """

    @classmethod
    def evaluate(cls, db: Session) -> Dict[str, Any]:
        # Query ground-truth labels and join with invoices
        labels = db.query(GroundTruthLabel).all()
        if not labels:
            return {"error": "No ground truth labels found in database"}

        label_map = {lbl.invoice_id: lbl for lbl in labels}
        invoices = db.query(InvoiceHeader).all()

        tp = 0
        fp = 0
        tn = 0
        fn = 0

        scenario_breakdown: Dict[str, Dict[str, int]] = {}
        total_injected_variance = 0.0
        total_detected_variance = 0.0

        for inv in invoices:
            gt = label_map.get(inv.id)
            if not gt:
                continue

            expected_is_anomaly = (gt.expected_verdict == "FAIL")
            actual_is_anomaly = (inv.validation_status == "FAILED" or inv.status in ["EXCEPTION_DISPUTED", "REJECTED"])

            scen = gt.scenario_type
            if scen not in scenario_breakdown:
                scenario_breakdown[scen] = {"total": 0, "detected": 0, "missed": 0, "false_alarms": 0}

            scenario_breakdown[scen]["total"] += 1
            if expected_is_anomaly:
                total_injected_variance += max(0.0, gt.injected_variance)

            if expected_is_anomaly and actual_is_anomaly:
                tp += 1
                scenario_breakdown[scen]["detected"] += 1
                total_detected_variance += max(0.0, inv.total_variance_amount)
            elif not expected_is_anomaly and actual_is_anomaly:
                fp += 1
                scenario_breakdown[scen]["false_alarms"] += 1
            elif not expected_is_anomaly and not actual_is_anomaly:
                tn += 1
            elif expected_is_anomaly and not actual_is_anomaly:
                fn += 1
                scenario_breakdown[scen]["missed"] += 1

        total_samples = tp + fp + tn + fn
        accuracy = round((tp + tn) / max(1, total_samples), 4)
        precision = round(tp / max(1, tp + fp), 4)
        recall = round(tp / max(1, tp + fn), 4)
        specificity = round(tn / max(1, tn + fp), 4)
        f1_score = round(2 * (precision * recall) / max(1e-6, precision + recall), 4) if (precision + recall) > 0 else 0.0

        # Credit note evaluations (Scenario 5)
        credit_notes = db.query(CreditNote).all()
        cn_total = len(credit_notes)
        cn_rejected = sum(1 for cn in credit_notes if cn.status == "REJECTED")
        cn_applied = sum(1 for cn in credit_notes if cn.status == "FULLY_APPLIED")

        # Scenario detection rate percentages
        breakdown_formatted = {}
        for scen, counts in scenario_breakdown.items():
            tot = counts["total"]
            det = counts["detected"]
            rate = round((det / max(1, tot)) * 100.0, 1) if scen != "NORMAL" else round(((tot - counts["false_alarms"]) / max(1, tot)) * 100.0, 1)
            breakdown_formatted[scen] = {
                "total_injected": tot,
                "detected": det,
                "missed": counts["missed"],
                "false_alarms": counts["false_alarms"],
                "detection_rate_pct": rate
            }

        return {
            "summary": {
                "total_invoices_audited": total_samples,
                "clean_invoices": tn + fp,
                "anomalous_invoices": tp + fn,
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
                "total_injected_variance_usd": round(total_injected_variance, 2),
                "total_detected_variance_usd": round(total_detected_variance, 2),
                "recovery_rate_pct": round((total_detected_variance / max(1.0, total_injected_variance)) * 100.0, 1),
            },
            "credit_note_reconciliation": {
                "total_credit_notes": cn_total,
                "reconciled_valid_credits": cn_applied,
                "blocked_excessive_credits": cn_rejected,
            },
            "scenario_breakdown": breakdown_formatted
        }
