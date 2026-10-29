"""
Ground-Truth Dataset Exporter for Freight Invoice Validation System.
Generates isolated ground_truth.csv and ground_truth.json datasets
containing expected decisions, expected exception types, and financial variances.
Kept strictly separate from operational validation input pipelines.
"""

import csv
import json
from pathlib import Path
from typing import Dict, Any, List
from sqlalchemy.orm import Session

from backend.app.models.ground_truth import GroundTruthLabel


class GroundTruthExporter:
    """
    Exports ground truth labels to CSV and JSON formats in an isolated evaluation store.
    """

    def __init__(self, output_dir: str = "data/exports/ground_truth"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export(self, db: Session) -> Dict[str, Any]:
        labels = db.query(GroundTruthLabel).order_by(GroundTruthLabel.label_id.asc()).all()

        columns = [
            "ground_truth_id",
            "affected_entity_type",
            "affected_entity_id",
            "issue_type",
            "expected_decision",
            "expected_exception_type",
            "expected_variance_amount",
            "anomaly_injection_id",
            "scenario_description"
        ]

        rows = []
        json_records = []

        for lbl in labels:
            # Map issue type to expected exception type
            exp_exc_type = "NONE"
            desc = "Clean baseline invoice matching contract"
            if lbl.issue_type == "UNKNOWN_SHIPMENT_REF":
                exp_exc_type = "UNMATCHED_SHIPMENT"
                desc = "Nonexistent external shipment reference staged on invoice"
            elif lbl.issue_type == "EXPIRED_RATE_CARD":
                exp_exc_type = "BASE_RATE_MISMATCH"
                desc = "Linehaul tariff schedule expired before shipment date"
            elif lbl.issue_type == "INCORRECT_WEIGHT_TIER":
                exp_exc_type = "WEIGHT_DISCREPANCY"
                desc = "Shipment misclassified into wrong weight tier pricing"
            elif lbl.issue_type == "DUPLICATE_FUEL_SURCHARGE":
                exp_exc_type = "DUPLICATE_BILLING"
                desc = "Secondary duplicate fuel surcharge assessed"
            elif lbl.issue_type == "DIMENSIONAL_WEIGHT_DISCREPANCY":
                exp_exc_type = "WEIGHT_DISCREPANCY"
                desc = "Volumetric density calculation discrepancy"
            elif lbl.issue_type == "UNAUTHORIZED_ACCESSORIAL":
                exp_exc_type = "UNAUTHORIZED_ACCESSORIAL"
                desc = "Accessorial billed without required operational proof"
            elif lbl.issue_type == "DUPLICATE_INVOICE":
                exp_exc_type = "DUPLICATE_BILLING"
                desc = "Repeat invoice billed for identical shipment and amount"
            elif lbl.issue_type == "EXCESSIVE_CREDIT_NOTE":
                exp_exc_type = "INVALID_CREDIT_NOTE"
                desc = "Credit note amount exceeds approved dispute limit"

            row = [
                lbl.label_id,
                "FreightInvoice",
                lbl.invoice_id,
                lbl.issue_type,
                lbl.expected_decision,
                exp_exc_type,
                lbl.injected_variance,
                lbl.anomaly_id or "NONE",
                desc
            ]
            rows.append(row)
            json_records.append(dict(zip(columns, row)))

        # 1. Write CSV
        csv_path = self.output_dir / "ground_truth.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            writer.writerows(rows)

        # 2. Write JSON
        json_path = self.output_dir / "ground_truth.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_records, f, indent=2, sort_keys=True)

        return {
            "output_directory": str(self.output_dir),
            "csv_file": str(csv_path),
            "json_file": str(json_path),
            "total_records": len(rows)
        }
