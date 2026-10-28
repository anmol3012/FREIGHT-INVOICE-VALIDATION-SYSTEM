# Source Code Manifest: Freight Invoice Validation System

This manifest catalogs every module, source file, test suite, and configuration file implemented in this project.

---

## 1. Directory Tree & Architecture

```
FREIGHT INVOICE VALIDATION SYSTEM/
│
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                     # FastAPI application entrypoint & static mount
│   │   ├── cli.py                      # CLI tool (seed, validate, evaluate, export, serve)
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── config.py               # Pydantic Settings & environment variables
│   │   │   └── database.py             # SQLAlchemy engine, session maker, SQLite PRAGMA
│   │   ├── models/
│   │   │   ├── __init__.py             # Model exports
│   │   │   ├── carrier.py              # Carrier master table
│   │   │   ├── rate_card.py            # RateCard, RateLane, AccessorialRule
│   │   │   ├── shipment.py             # Shipment, WeightMeasurement, DeliveryRecord, AccessorialEvent
│   │   │   ├── invoice.py              # InvoiceHeader, InvoiceLine
│   │   │   ├── exception.py            # InvoiceException
│   │   │   ├── credit_note.py          # CreditNote
│   │   │   ├── audit.py                # AuditEvent immutable log
│   │   │   └── ground_truth.py         # GroundTruthLabel independent evaluation store
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   └── api_schemas.py          # Pydantic request & response models
│   │   ├── engine/
│   │   │   ├── __init__.py
│   │   │   ├── calculator.py           # Contractual freight rating & billable weight calculation
│   │   │   ├── validator.py            # Invoice reconciliation, tolerances & duplicate detection
│   │   │   └── evaluator.py            # Confusion matrix & benchmark accuracy evaluation
│   │   ├── generator/
│   │   │   ├── __init__.py
│   │   │   ├── generator.py            # Deterministic synthetic data generator (seed: 20261022)
│   │   │   └── exporter.py             # CSV, JSON, SQL seed exporter & SHA-256 checksums
│   │   └── api/
│   │       ├── __init__.py
│   │       └── routes/
│   │           ├── __init__.py
│   │           └── api.py              # REST API endpoints (KPIs, Invoices, Exceptions, Credits, Eval)
│   └── requirements.txt                # Backend dependencies (FastAPI, SQLAlchemy, Pytest, Pydantic)
│
├── frontend/
│   ├── package.json                    # Frontend dependencies (React 19, TypeScript, Lucide, Recharts)
│   ├── vite.config.ts                  # Vite build configuration
│   ├── tsconfig.json                   # TypeScript configuration
│   ├── index.html                      # HTML root template
│   ├── dist/                           # Production static bundle (mounted directly by FastAPI)
│   └── src/
│       ├── main.tsx                    # React client entry point
│       ├── App.tsx                     # Operations Dashboard UI with tabs, KPIs, and slideout drawer
│       └── index.css                   # Responsive dark-theme styling, status badges & tables
│
├── tests/
│   ├── __init__.py
│   ├── test_calculation_engine.py      # Contractual calculation engine unit tests
│   ├── test_negative_scenarios.py      # All 5 mandatory negative scenarios validation tests
│   ├── test_determinism.py             # Dual-run SHA-256 seed determinism tests
│   └── test_api_endpoints.py           # REST API integration tests
│
├── docs/
│   ├── data_dictionary.md              # Complete entity schema and column specifications
│   ├── architecture.md                 # System architecture, engines, and workflow lifecycle
│   ├── source_manifest.md              # Source code inventory and component descriptions
│   └── validation_report.md            # Ground-truth evaluation metrics and checksum verification
│
├── data/
│   └── exports/                        # Multi-format exported seeds (CSV, JSON, SQL)
│       ├── csv/
│       ├── json/
│       ├── sql/
│       └── checksums.sha256            # SHA-256 cryptographic manifest
│
├── Dockerfile                          # Production multi-stage Docker deployment build
├── docker-compose.yml                  # Docker Compose orchestrating app and PostgreSQL
├── pytest.ini                          # Pytest configuration
└── README.md                           # Comprehensive user and architecture documentation
```

---

## 2. Component Descriptions

| File / Module | Responsibility |
|---|---|
| `backend/app/models/carrier.py` | Models carrier credentials, SCAC codes, payment terms, and relationships. |
| `backend/app/models/rate_card.py` | Contracted tariffs, rate lanes, CWT rates, mileage rates, and accessorial rules. |
| `backend/app/models/shipment.py` | Operational shipments, certified scale weights, dimensional calculations, and POD delivery receipts. |
| `backend/app/models/invoice.py` | Invoices and line items with SHA-256 duplicate fingerprinting and status state machine. |
| `backend/app/models/exception.py` | Actionable audit exceptions with severity levels, variance amounts, and root-cause codes. |
| `backend/app/models/credit_note.py`| Credit note reconciliation and over-credit balance protection. |
| `backend/app/models/audit.py` | Write-only immutable audit trail capturing actor, event type, and payload snapshots. |
| `backend/app/models/ground_truth.py`| Isolated synthetic truth labels for benchmarking evaluation metrics. |
| `backend/app/engine/calculator.py` | Exact rating formulas: CWT, per-mile, flat, minimum floor, FSC pegs, and accessorial proof checks. |
| `backend/app/engine/validator.py` | Multi-line reconciliation, tolerance comparison, accessorial proof verification, duplicate checking. |
| `backend/app/engine/evaluator.py` | Confusion Matrix (TP, FP, TN, FN), Precision, Recall, F1, Accuracy, and financial recovery metrics. |
| `backend/app/generator/generator.py`| Deterministic generator using seed 20261022 supporting Starter and Full (100 carriers / 20k shipments / 15k invoices) configurations. |
| `backend/app/generator/exporter.py`| Multi-format dataset export to CSV, JSON, and SQL with SHA-256 manifest. |
| `frontend/src/App.tsx` | Production-grade operations dashboard featuring KPIs, drilldown drawer, exception triage, and evaluation matrix. |
| `backend/app/cli.py` | Unified CLI tool for `seed`, `validate`, `evaluate`, `export`, and `serve`. |
