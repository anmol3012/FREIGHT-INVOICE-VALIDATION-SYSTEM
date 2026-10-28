import argparse
import sys
from sqlalchemy import text
from backend.app.core.database import SessionLocal, engine, Base
from backend.app.core.config import settings
from backend.app.generator.generator import DeterministicDataGenerator
from backend.app.generator.exporter import DataExporter

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
    finally:
        db.close()

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

    args = parser.parse_args()
    if args.command == "seed":
        cmd_seed(args)
    elif args.command == "export":
        cmd_export(args)
    elif args.command == "serve":
        cmd_serve(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
