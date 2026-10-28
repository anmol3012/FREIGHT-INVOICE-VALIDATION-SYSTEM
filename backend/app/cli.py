import argparse
import sys
from backend.app.core.database import SessionLocal, engine, Base
from backend.app.core.config import settings
from backend.app.generator.generator import SyntheticDataGenerator
from backend.app.generator.exporter import DataExporter
from backend.app.engine.validator import InvoiceValidator
from backend.app.engine.evaluator import AuditEvaluator
from backend.app.models.invoice import InvoiceHeader
from backend.app.models.credit_note import CreditNote

def init_db(reset=False):
    if reset:
        Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

def cmd_seed(args):
    init_db(reset=args.reset)
    db = SessionLocal()
    try:
        scale = args.scale
        seed = args.seed or settings.DEFAULT_RANDOM_SEED
        print(f"Generating synthetic freight dataset [Scale: {scale.upper()}, Seed: {seed}]...")

        if scale == "full":
            num_c = settings.FULL_CARRIERS
            num_s = settings.FULL_SHIPMENTS
            num_i = settings.FULL_INVOICES
        else:
            num_c = settings.STARTER_CARRIERS
            num_s = settings.STARTER_SHIPMENTS
            num_i = settings.STARTER_INVOICES

        generator = SyntheticDataGenerator(seed=seed)
        counts = generator.generate_all(db, num_carriers=num_c, num_shipments=num_s, num_invoices=num_i)
        print(f"Synthesis Complete: {counts}")
    finally:
        db.close()

def cmd_validate(args):
    init_db()
    db = SessionLocal()
    try:
        invoices = db.query(InvoiceHeader).all()
        print(f"Validating {len(invoices)} invoices against contractual rates and delivery records...")
        passed = 0
        failed = 0
        for inv in invoices:
            v_inv = InvoiceValidator.validate_invoice(db, inv.id)
            if v_inv.validation_status == "PASSED":
                passed += 1
            else:
                failed += 1

        print(f"Validation completed: {passed} PASSED within tolerance, {failed} DISCREPANCIES / EXCEPTIONS raised.")

        # Reconcile credit notes
        credit_notes = db.query(CreditNote).all()
        print(f"Reconciling {len(credit_notes)} credit notes...")
        for cn in credit_notes:
            InvoiceValidator.validate_credit_note(db, cn.id)
        print("Credit note reconciliation finished.")
    finally:
        db.close()

def cmd_evaluate(args):
    init_db()
    db = SessionLocal()
    try:
        results = AuditEvaluator.evaluate(db)
        print("\n================ AUDIT DETECTION EVALUATION ================")
        print(f"Total Invoices Audited:  {results['summary']['total_invoices_audited']}")
        print(f"True Positives (TP):     {results['summary']['true_positives']}")
        print(f"False Positives (FP):    {results['summary']['false_positives']}")
        print(f"True Negatives (TN):     {results['summary']['true_negatives']}")
        print(f"False Negatives (FN):    {results['summary']['false_negatives']}")
        print("------------------------------------------------------------")
        print(f"Precision:               {results['metrics']['precision']:.4f}")
        print(f"Recall (Sensitivity):    {results['metrics']['recall']:.4f}")
        print(f"F1-Score:                {results['metrics']['f1_score']:.4f}")
        print(f"Accuracy:                {results['metrics']['accuracy']:.4f}")
        print("------------------------------------------------------------")
        print(f"Injected Leakage:        ${results['financial_impact']['total_injected_variance_usd']:,.2f}")
        print(f"Recovered Variance:      ${results['financial_impact']['total_detected_variance_usd']:,.2f} ({results['financial_impact']['recovery_rate_pct']}%)")
        print("============================================================\n")
    finally:
        db.close()

def cmd_export(args):
    init_db()
    db = SessionLocal()
    try:
        exporter = DataExporter(output_dir=args.output_dir or "data/exports")
        res = exporter.export_all(db)
        print(f"Exported all datasets successfully to: {res['output_directory']}")
        print(f"Checksum manifest written to: {res['manifest_file']}")
        for f, h in res['file_checksums'].items():
            print(f"  {f}: {h[:16]}...")
    finally:
        db.close()

def cmd_serve(args):
    import uvicorn
    init_db()
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
    p_seed.add_argument("--scale", choices=["starter", "full"], default="starter", help="Dataset scale")
    p_seed.add_argument("--seed", type=int, default=settings.DEFAULT_RANDOM_SEED, help="Random seed")
    p_seed.add_argument("--reset", action="store_true", help="Reset database before seeding")

    # validate
    p_val = subparsers.add_parser("validate", help="Run contractual validation engine")
    p_val.add_argument("--all", action="store_true", help="Validate all invoices")

    # evaluate
    subparsers.add_parser("evaluate", help="Evaluate detection against ground truth")

    # export
    p_exp = subparsers.add_parser("export", help="Export datasets to CSV, JSON, and SQL")
    p_exp.add_argument("--output-dir", default="data/exports", help="Export target directory")

    args = parser.parse_args()
    if args.command == "seed":
        cmd_seed(args)
    elif args.command == "validate":
        cmd_validate(args)
    elif args.command == "evaluate":
        cmd_evaluate(args)
    elif args.command == "export":
        cmd_export(args)
    elif args.command == "serve":
        cmd_serve(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
