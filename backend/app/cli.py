import argparse
import sys
from sqlalchemy import text
from backend.app.core.database import SessionLocal, engine, Base
from backend.app.core.config import settings
from backend.app.generator.generator import DeterministicDataGenerator
from backend.app.generator.exporter import DataExporter
from backend.app.generator.ground_truth_exporter import GroundTruthExporter
from backend.app.generator.data_quality import DataQualityValidator
from backend.app.generator.reproducibility import ReproducibilityVerifier
from backend.app.engine.validator import FreightInvoiceValidator
from backend.app.engine.credit_note_service import CreditNoteService
from backend.app.engine.evaluator import AuditEvaluator
from backend.app.models.invoice import FreightInvoice
from backend.app.models.credit_note import CreditNote

def init_db(reset: bool = False):
    with engine.connect() as conn:
        if reset:
            # Safely disable foreign key enforcement during schema drop/rebuild
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            Base.metadata.drop_all(bind=engine)
            conn.execute(text("PRAGMA foreign_keys = ON"))
        Base.metadata.create_all(bind=engine)

def cmd_seed(args):
    init_db(reset=args.reset)
    db = SessionLocal()
    try:
        scale = args.scale
        seed = args.seed if args.seed is not None else 20261022
        print(f"Generating synthetic freight dataset [Scale: {scale.upper()}, Seed: {seed}]...")

        generator = DeterministicDataGenerator(profile_name=scale, seed=seed)
        counts = generator.generate_all(db)
        print("Synthesis Complete!")
        for entity, count in counts.items():
            print(f"  - {entity}: {count}")
    finally:
        db.close()

def cmd_export(args):
    init_db(reset=False)
    db = SessionLocal()
    try:
        seed = args.seed if args.seed is not None else 20261022
        exporter = DataExporter(output_dir=args.output_dir or "data/exports")
        res = exporter.export_all(db, seed=seed)
        print(f"Exported all datasets successfully to: {res['output_directory']}")
        print(f"Manifest written to: {res['manifest_file']}")
        print(f"Checksum manifest written to: {res['checksums_file']}")
        for f, h in sorted(res['file_checksums'].items()):
            print(f"  {f}: {h[:16]}...")

        # Export isolated ground truth dataset
        gt_exporter = GroundTruthExporter(output_dir="data/exports/ground_truth")
        gt_res = gt_exporter.export(db)
        print(f"\nGround Truth Dataset exported to: {gt_res['output_directory']}")
        print(f"  CSV:  {gt_res['csv_file']}")
        print(f"  JSON: {gt_res['json_file']} ({gt_res['total_records']} labels)")
    finally:
        db.close()

def cmd_evaluate(args):
    init_db(reset=False)
    db = SessionLocal()
    try:
        res = AuditEvaluator.evaluate(db)
        if "error" in res:
            print(f"Evaluation Error: {res['error']}")
            return

        s = res["summary"]
        m = res["metrics"]
        f = res["financial_impact"]

        print("\n==================== AUDIT DETECTION EVALUATION ====================")
        print(f"Total Invoices Processed:   {s['total_invoices_processed']}")
        print(f"Valid Invoices (Match):     {s['valid_invoices']}")
        print(f"Invoices Requiring Review:  {s['invoices_requiring_review']}")
        print(f"Rejected Invoices:          {s['rejected_invoices']}")
        print("--------------------------------------------------------------------")
        print(f"True Positives (TP):        {s['true_positives']}")
        print(f"False Positives (FP):       {s['false_positives']}")
        print(f"True Negatives (TN):        {s['true_negatives']}")
        print(f"False Negatives (FN):       {s['false_negatives']}")
        print("--------------------------------------------------------------------")
        print(f"Accuracy:                   {m['accuracy']:.4f}")
        print(f"Precision:                  {m['precision']:.4f}")
        print(f"Recall (Sensitivity):       {m['recall']:.4f}")
        print(f"Specificity:                {m['specificity']:.4f}")
        print(f"F1-Score:                   {m['f1_score']:.4f}")
        print("--------------------------------------------------------------------")
        print(f"Total Detected Exceptions:  {s['total_detected_exceptions']}")
        print(f"Unresolved Exceptions:      {s['unresolved_exceptions']}")
        print(f"Duplicate Invoices Detected: {s['duplicate_invoices_detected']}")
        print(f"Duplicate Surcharges (FSC): {s['duplicate_surcharges_detected']}")
        print(f"Data-Integrity Failures:    {s['data_integrity_failures']}")
        print("--------------------------------------------------------------------")
        print(f"Injected Overbilling:       ${f['total_injected_overbilling_usd']:,.2f}")
        print(f"Detected Overbilling:       ${f['total_detected_overbilling_usd']:,.2f} ({f['recovery_rate_pct']}%)")
        print(f"Approved Credit Value:      ${f['total_approved_credit_usd']:,.2f}")
        print(f"Reconciled Credit Value:    ${f['total_reconciled_credit_usd']:,.2f}")
        print(f"Rejected Credit Value:      ${f['total_rejected_credit_usd']:,.2f}")
        print("====================================================================\n")

        print("--- Negative Scenario Breakdown ---")
        for scen, sc_data in res["scenario_breakdown"].items():
            print(f"  [{scen}]: {sc_data['detected']}/{sc_data['total_injected']} detected ({sc_data['detection_rate_pct']}%) | Missed: {sc_data['missed']} | Injected: ${sc_data['injected_variance']:,.2f}")
    finally:
        db.close()

def cmd_validate(args):
    init_db(reset=False)
    db = SessionLocal()
    try:
        inv_id = args.invoice_id
        if inv_id:
            invoices = db.query(FreightInvoice).filter(FreightInvoice.invoice_id == inv_id).all()
        else:
            invoices = db.query(FreightInvoice).all()

        print(f"Running Contractual Freight Validation on {len(invoices)} invoices...")
        passed = 0
        failed = 0
        total_variance_recovered = 0.0

        for inv in invoices:
            summary = FreightInvoiceValidator.validate_invoice(db, inv.invoice_id)
            if summary.overall_verdict == "PASSED":
                passed += 1
            else:
                failed += 1
                total_variance_recovered += max(0.0, summary.variance_amount)

        print(f"\n--- Validation Summary ---")
        print(f"Total Invoices Audited: {len(invoices)}")
        print(f"Passed (Match):         {passed}")
        print(f"Failed (Exceptions):    {failed}")
        print(f"Disputed Variance:      ${total_variance_recovered:,.2f}")

        # Credit note reconciliation
        credit_notes = db.query(CreditNote).all()
        print(f"\nReconciling {len(credit_notes)} carrier credit notes against disputes...")
        cn_approved = 0
        cn_rejected = 0
        for cn in credit_notes:
            cn_res = CreditNoteService.validate_credit_note(db, cn.credit_note_id)
            if cn_res.is_valid:
                cn_approved += 1
            else:
                cn_rejected += 1
        print(f"Credit Notes Approved:  {cn_approved}")
        print(f"Credit Notes Rejected:  {cn_rejected} (Scenario E protected)")
    finally:
        db.close()

def cmd_check_quality(args):
    init_db(reset=False)
    db = SessionLocal()
    try:
        print("Running Comprehensive Data-Quality Audit across all entities...")
        validator = DataQualityValidator(db)
        res = validator.export_reports(output_dir=args.output_dir or "data/exports")
        summary = validator.run_all_checks()
        print(f"\n--- Data Quality Audit Result: [{summary['dataset_status']}] ---")
        print(f"  Unintentional Defects: {summary['unintentional_defects_count']}")
        print(f"  Intentional Test Anomalies: {summary['intentional_anomalies_count']}")
        print(f"  JSON Summary: {res['json_summary']}")
        print(f"  Markdown Report: {res['markdown_summary']}")
        print(f"  Docs Report: {res['documentation_report']}")
    finally:
        db.close()

def cmd_verify_reproducibility(args):
    scale = args.scale or "starter"
    seed = args.seed if args.seed is not None else 20261022
    print(f"Running Dual-Run Reproducibility Verification [Scale: {scale}, Seed: {seed}]...")
    res = ReproducibilityVerifier.verify(profile_name=scale, seed=seed)
    print(f"\n--- Reproducibility Result: [{'100% REPRODUCIBLE (PASS)' if res['reproducible'] else 'FAILED'}] ---")
    print(f"  Entities Compared: {res['entities_compared']}")
    print(f"  Files Compared:    {res['files_compared']}")
    print(f"  Hash Mismatches:   {res['mismatches_count']}")
    if not res["reproducible"]:
        for m in res["mismatches"]:
            print(f"    - {m}")
    else:
        print("  All CSV, JSON, and SQL exports are bit-for-bit identical across dual runs!")

def cmd_serve(args):
    import uvicorn
    init_db(reset=False)
    host = args.host or "127.0.0.1"
    port = args.port or 8000
    print(f"Starting Freight Invoice Validation System server on http://{host}:{port} ...")
    uvicorn.run("backend.app.main:app", host=host, port=port, reload=args.reload)

def main():
    parser = argparse.ArgumentParser(description="Freight Invoice Validation System CLI")
    subparsers = parser.add_subparsers(dest="command", help="Sub-commands")

    # serve
    p_srv = subparsers.add_parser("serve", help="Launch FastAPI server and dashboard")
    p_srv.add_argument("--host", default="127.0.0.1", help="Host address")
    p_srv.add_argument("--port", type=int, default=8000, help="Port number")
    p_srv.add_argument("--reload", action="store_true", help="Enable live auto-reload")

    # seed
    p_seed = subparsers.add_parser("seed", help="Generate synthetic logistics dataset")
    p_seed.add_argument("--scale", choices=["test", "starter", "full"], default="starter", help="Dataset scale")
    p_seed.add_argument("--seed", type=int, default=20261022, help="Random seed")
    p_seed.add_argument("--reset", action="store_true", help="Reset database before seeding")

    # export
    p_exp = subparsers.add_parser("export", help="Export datasets to CSV, JSON, and SQL")
    p_exp.add_argument("--output-dir", default="data/exports", help="Export target directory")
    p_exp.add_argument("--seed", type=int, default=20261022, help="Seed value for manifest")

    # validate
    p_val = subparsers.add_parser("validate", help="Run 20-step validation engine on invoices")
    p_val.add_argument("--invoice-id", help="Validate specific invoice ID (default: all)")

    # evaluate
    subparsers.add_parser("evaluate", help="Evaluate audit detection accuracy against ground truth")

    # check-quality
    p_qual = subparsers.add_parser("check-quality", help="Run comprehensive data-quality checks")
    p_qual.add_argument("--output-dir", default="data/exports", help="Export target directory")

    # verify-reproducibility
    p_rep = subparsers.add_parser("verify-reproducibility", help="Run dual-run reproducibility test")
    p_rep.add_argument("--scale", choices=["test", "starter", "full"], default="starter", help="Dataset scale")
    p_rep.add_argument("--seed", type=int, default=20261022, help="Random seed")

    args = parser.parse_args()
    if args.command == "seed":
        cmd_seed(args)
    elif args.command == "export":
        cmd_export(args)
    elif args.command == "validate":
        cmd_validate(args)
    elif args.command == "evaluate":
        cmd_evaluate(args)
    elif args.command == "check-quality":
        cmd_check_quality(args)
    elif args.command == "verify-reproducibility":
        cmd_verify_reproducibility(args)
    elif args.command == "serve":
        cmd_serve(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
