"""
Automated Test for Full-Scale Acceptance Criteria (Phase 7).

Validates:
1. Execution of full-scale dataset (100 carriers, 20,000 shipments, 15,000 invoices).
2. Detection metrics and confusion matrix against ground truth.
3. Non-empty checksums and manifest verification.
"""

import os
import json
import pytest

BENCHMARK_RESULT_PATH = "data/full_scale_benchmark_results.json"


def test_full_scale_benchmark_metrics():
    """Verifies that the full-scale benchmark succeeded and met all acceptance criteria."""
    if not os.path.exists(BENCHMARK_RESULT_PATH):
        pytest.skip(f"Full-scale benchmark results file '{BENCHMARK_RESULT_PATH}' not yet generated.")

    with open(BENCHMARK_RESULT_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 1. Profile and Seed
    assert data["profile"] == "full"
    assert data["seed"] == 20261022

    # 2. Row counts
    counts = data["row_counts"]
    assert counts["carriers"] == 100
    assert counts["shipments"] == 20000
    assert counts["freight_invoices"] == 15000
    assert counts["invoice_lines"] >= 15000
    assert counts["ground_truth_labels"] == 15000

    # 3. Validation Findings
    val = data["validation_findings"]
    assert val["total_audited"] == 15000
    assert val["passed_clean_match"] > 0
    assert val["discrepancies_flagged"] > 0
    assert val["passed_clean_match"] + val["discrepancies_flagged"] == 15000

    # 4. Evaluation Metrics
    m = data["accuracy_metrics"]
    assert m["accuracy"] >= 0.95
    assert m["precision"] >= 0.95
    assert m["recall"] >= 0.95
    assert m["f1_score"] >= 0.95

    # 5. Confusion Matrix
    cm = data["confusion_matrix"]
    total_eval = cm["true_positives"] + cm["false_positives"] + cm["true_negatives"] + cm["false_negatives"]
    assert total_eval == 15000

    # 6. Export integrity (if exports directory is present on host)
    manifest_path = data.get("export_manifest", "").replace("\\", "/")
    checksums_path = data.get("export_checksums", "").replace("\\", "/")
    if os.path.exists(manifest_path):
        assert os.path.getsize(manifest_path) > 0
    if os.path.exists(checksums_path):
        assert os.path.getsize(checksums_path) > 0
