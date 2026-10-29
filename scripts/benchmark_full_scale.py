"""
Full-Scale Acceptance Verification Script (Phase 7).

Executes full-scale synthetic generation and 20-step validation engine:
- 100 carriers
- 250 lanes
- 20,000 shipments
- 15,000 freight invoices
Measures exact runtime, row counts, validation findings, detection metrics, and export checksums.
"""

import time
import os
import sys
import json
import sqlite3
from datetime import datetime

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.app.core.database import Base
from backend.app.generator.generator import DeterministicDataGenerator
from backend.app.generator.exporter import DataExporter
from backend.app.generator.ground_truth_exporter import GroundTruthExporter
from backend.app.engine.validator import FreightInvoiceValidator
from backend.app.engine.evaluator import AuditEvaluator
from backend.app.models.invoice import FreightInvoice


def run_full_scale_acceptance(db_path: str = "data/full_scale_benchmark.db", seed: int = 20261022):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    if os.path.exists(db_path):
        os.remove(db_path)

    print("====================================================================")
    print("      FREIGHT INVOICE VALIDATION SYSTEM - FULL-SCALE ACCEPTANCE      ")
    print("====================================================================")
    print(f"Target Configuration:")
    print(f"  - Carriers:          100")
    print(f"  - Shipments:         20,000")
    print(f"  - Freight Invoices:  15,000")
    print(f"  - Random Seed:       {seed}")
    print(f"  - Database Target:   {db_path}")
    print("--------------------------------------------------------------------")

    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False}
    )
    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode = WAL;"))
        conn.execute(text("PRAGMA synchronous = NORMAL;"))
        conn.execute(text("PRAGMA cache_size = -64000;")) # 64MB RAM cache
        conn.execute(text("PRAGMA temp_store = MEMORY;"))

    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = Session()

    t_start = time.time()

    # Step 1: Synthesis
    print("\n[Step 1/4] Executing 17-step dependency generation pipeline...")
    t_gen_start = time.time()
    generator = DeterministicDataGenerator(profile_name="full", seed=seed)
    counts = generator.generate_all(db)
    t_gen_elapsed = round(time.time() - t_gen_start, 2)
    print(f"Generation completed in {t_gen_elapsed}s.")
    for entity, count in sorted(counts.items()):
        print(f"  - {entity}: {count:,}")

    # Step 2: Full-Scale 20-Step Freight Audit
    print("\n[Step 2/4] Executing 20-step contractual freight audit on all invoices...")
    t_val_start = time.time()
    invoices = db.query(FreightInvoice).all()
    passed = 0
    failed = 0
    total_recovered = 0.0

    # Batch commit every 1000 validations
    for idx, inv in enumerate(invoices, start=1):
        summary = FreightInvoiceValidator.validate_invoice(db, inv.invoice_id)
        if summary.overall_verdict == "PASSED":
            passed += 1
        else:
            failed += 1
            total_recovered += max(0.0, summary.variance_amount)

        if idx % 2500 == 0:
            db.commit()
            print(f"  ... audited {idx:,}/{len(invoices):,} invoices (Passed: {passed:,}, Exceptions: {failed:,})")

    db.commit()
    t_val_elapsed = round(time.time() - t_val_start, 2)
    print(f"Audit completed in {t_val_elapsed}s ({round(len(invoices) / max(0.1, t_val_elapsed), 1)} invoices/sec).")
    print(f"  Passed Match:        {passed:,} ({round(passed / len(invoices) * 100, 2)}%)")
    print(f"  Exceptions Raised:   {failed:,} ({round(failed / len(invoices) * 100, 2)}%)")
    print(f"  Disputed Recovered:  ${total_recovered:,.2f}")

    # Step 3: Evaluation Against Independent Ground Truth
    print("\n[Step 3/4] Evaluating detection accuracy against isolated ground-truth labels...")
    eval_res = AuditEvaluator.evaluate(db)
    m = eval_res["metrics"]
    s = eval_res["summary"]
    f = eval_res["financial_impact"]

    print(f"  Accuracy:            {m['accuracy'] * 100:.2f}%")
    print(f"  Precision:           {m['precision'] * 100:.2f}%")
    print(f"  Recall:              {m['recall'] * 100:.2f}%")
    print(f"  F1-Score:            {m['f1_score'] * 100:.2f}%")
    print(f"  Confusion Matrix:    TP={s['true_positives']:,}, FP={s['false_positives']:,}, TN={s['true_negatives']:,}, FN={s['false_negatives']:,}")
    print(f"  Financial Recovery:  ${f['total_detected_overbilling_usd']:,.2f} of ${f['total_injected_overbilling_usd']:,.2f} ({f['recovery_rate_pct']}%)")

    # Step 4: Multi-Format Exports and SHA-256 Checksums
    print("\n[Step 4/4] Exporting full datasets to CSV, JSON, and SQL Seed...")
    export_dir = "data/full_scale_exports"
    exporter = DataExporter(output_dir=export_dir)
    exp_res = exporter.export_all(db, seed=seed)
    
    gt_exporter = GroundTruthExporter(output_dir=os.path.join(export_dir, "ground_truth"))
    gt_res = gt_exporter.export(db)

    t_total_elapsed = round(time.time() - t_start, 2)

    db.close()

    db_size_mb = round(os.path.getsize(db_path) / (1024 * 1024), 2)
    print("\n====================================================================")
    print("                   FULL-SCALE ACCEPTANCE SUMMARY                    ")
    print("====================================================================")
    print(f"Total Execution Time:   {t_total_elapsed}s ({round(t_total_elapsed / 60, 2)} minutes)")
    print(f"Database File Size:     {db_size_mb} MB")
    print(f"Total Tables Populated: 17")
    print(f"Total Database Rows:    {sum(counts.values()):,}")
    print(f"Export Checksums File:  {exp_res['checksums_file']}")
    print(f"Manifest File:          {exp_res['manifest_file']}")
    print("====================================================================\n")

    # Save benchmark metrics artifact
    benchmark_report = {
        "benchmark_timestamp": datetime.utcnow().isoformat(),
        "profile": "full",
        "seed": seed,
        "database_size_mb": db_size_mb,
        "timings": {
            "generation_seconds": t_gen_elapsed,
            "validation_seconds": t_val_elapsed,
            "total_runtime_seconds": t_total_elapsed
        },
        "row_counts": counts,
        "validation_findings": {
            "total_audited": len(invoices),
            "passed_clean_match": passed,
            "discrepancies_flagged": failed,
            "total_disputed_usd": round(total_recovered, 2)
        },
        "accuracy_metrics": m,
        "confusion_matrix": s,
        "financial_impact": f,
        "export_manifest": exp_res["manifest_file"],
        "export_checksums": exp_res["checksums_file"]
    }

    with open("data/full_scale_benchmark_results.json", "w", encoding="utf-8") as f_out:
        json.dump(benchmark_report, f_out, indent=2)

    return benchmark_report


if __name__ == "__main__":
    run_full_scale_acceptance()
