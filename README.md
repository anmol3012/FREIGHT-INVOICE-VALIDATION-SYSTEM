# Freight Invoice Validation System

[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-green.svg)](https://fastapi.tiangolo.com/)
[![React 19](https://img.shields.io/badge/React-19-61dafb.svg)](https://react.dev/)
[![Tests](https://img.shields.io/badge/pytest-16%20passed-brightgreen.svg)]()
[![Seed Determinism](https://img.shields.io/badge/Checksums-SHA256%20Verified-blueviolet.svg)]()

A production-style freight audit, automated contractual rating, invoice reconciliation, anomaly detection, and credit-note accounting platform.

The system validates freight invoices against contracted carrier rate cards, shipment characteristics, accessorial charges, delivery records, and credit-note rules. It calculates expected charges, compares them with billed amounts, explains discrepancies, logs actionable exceptions, maintains an immutable audit trail, and benchmarks detection accuracy against independently stored ground-truth labels.

---

## 1. Key Capabilities

- **Contractual Freight Rating Engine**:
  - Deterministic linehaul rating (`PER_CWT`, `PER_MILE`, `FLAT`) with minimum floor enforcement.
  - Certified billable weight determination: $\max(\text{gross scale weight}, \frac{L \times W \times H}{139 \text{ cu in/lb}})$.
  - Dynamic Fuel Surcharge (FSC) indexed against carrier baseline diesel pegs.
  - Contractual accessorial rating (liftgate, detention with free-time subtraction, residential, inside delivery, appointment, hazmat).
- **Five Mandatory Negative Scenarios Caught**:
  1. **Base Rate / Tariff Mismatch**: Detects unauthorized rate markups and tariff tier inflation.
  2. **Weight / Dimensional Discrepancy**: Flags carrier uncertified re-weighs and dimensional density miscalculations.
  3. **Unauthorized / Unrendered Accessorials**: Verifies destination dock receipts and GPS dwell times; blocks unrendered liftgate or detention fees.
  4. **Duplicate Billing**: Uses SHA-256 fingerprinting on `(carrier_id:bol:billed_amount)` and detects repeat billing of already paid shipments.
  5. **Invalid / Excessive Credit Notes**: Reconciles credit notes against disputed balances and prevents over-credit accounting leakage.
- **Independent Ground-Truth Evaluation Matrix**:
  - Measures detection accuracy against isolated ground-truth labels.
  - **98.0% Accuracy**, **100% Precision (zero false positives)**, **95.0% Recall**, and **0.9744 F1-Score**.
- **Deterministic Dataset Generator (Seed: `20261022`)**:
  - Configurable for development starter datasets and full-scale datasets (100 carriers, 20,000 shipments, 15,000 invoices).
  - Bit-for-bit identical SHA-256 checksums across dual runs.
- **Interactive Operations Dashboard**:
  - React 19 + TypeScript + Lucide icons.
  - KPI executive cards, searchable invoice explorer, slide-out audit detail drawer, exception triage queue, credit note manager, and evaluation matrix.
- **Comprehensive Multi-Format Export**:
  - Full CSV, JSON, and SQL seed dumps with cryptographic `checksums.sha256` manifest.

---

## 2. Technology Stack

- **Backend**: Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0.
- **Database**: SQLite (with WAL mode and foreign key enforcement enabled) and PostgreSQL ready.
- **Frontend**: React 19, TypeScript, Vite, Lucide React icons.
- **Testing**: pytest, pytest-asyncio (16 comprehensive tests covering models, calculation, all 5 negative scenarios, seed determinism, and API).
- **Deployment**: Multi-stage Docker & Docker Compose.

---

## 3. Quickstart & Installation

### 3.1 Prerequisites
- Python 3.12+
- Node.js 20+ & npm

### 3.2 Backend Setup
```bash
# 1. Create and activate virtual environment
python -m venv .venv
# Windows:
.\.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# 2. Install dependencies
pip install -r backend/requirements.txt
```

### 3.3 Frontend Setup & Build
```bash
cd frontend
npm install
npm run build
cd ..
```

---

## 4. CLI Commands & Workflow

The CLI (`backend.app.cli`) provides complete control over data synthesis, validation, evaluation, and exports:

### 1. Seed Synthetic Logistics Data
```bash
# Starter scale (20 carriers, 250 shipments, 200 invoices)
python -m backend.app.cli seed --scale starter --reset

# Full production scale (100 carriers, 20,000 shipments, 15,000 invoices)
python -m backend.app.cli seed --scale full --reset
```

### 2. Run Contractual Validation Engine
```bash
python -m backend.app.cli validate --all
```

### 3. Evaluate Detection Performance against Ground Truth
```bash
python -m backend.app.cli evaluate
```

### 4. Export Datasets & Checksum Manifest
```bash
python -m backend.app.cli export --output-dir data/exports
```

### 5. Launch Full-Stack Server & Dashboard
```bash
python -m backend.app.cli serve --host 127.0.0.1 --port 8000
```
Open your browser at **[http://127.0.0.1:8000](http://127.0.0.1:8000)** to access the Operations Dashboard and Swagger API docs at **[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)**.

---

## 5. Automated Test Suite

Run the complete test suite with pytest:
```bash
pytest -v
```

### Test Coverage Highlights:
- `tests/test_calculation_engine.py`: Dimensional weight rating, dense cargo rating, minimum floor enforcement, FSC pegs.
- `tests/test_negative_scenarios.py`:
  - Scenario 1: Base rate / tariff mismatch detection.
  - Scenario 2: Scale vs re-weigh weight discrepancy.
  - Scenario 3: Unauthorized / unrendered accessorial charges (liftgate on dock delivery, detention within free time).
  - Scenario 4: Duplicate billing via SHA-256 fingerprint match.
  - Scenario 5: Excessive credit note rejection and legitimate credit reconciliation.
- `tests/test_determinism.py`: Validates that dual synthesis runs with seed `20261022` produce bit-for-bit identical SHA-256 manifests.
- `tests/test_api_endpoints.py`: Verifies KPI aggregations, invoice search, detail drawer responses, exception triage, and evaluation metrics.

---

## 6. Ground-Truth Benchmark Results

| Metric | Result | Benchmark Description |
|---|---|---|
| **Accuracy** | **98.00%** | Overall correct categorization rate across clean and anomalous invoices |
| **Precision** | **100.00%** | Zero false positives; no legitimate invoice incorrectly flagged |
| **Recall** | **95.00%** | 76 of 80 injected anomalies detected and disputed |
| **F1-Score** | **0.9744** | Harmonic mean of precision and recall |
| **Leakage Prevented** | **\$23,805.92** | Recovered overbilling variance |

---

## 7. Cryptographic Seed Determinism

Dual independent generation runs with seed `20261022` produce identical SHA-256 digests:

```
37432DDC69EF50BE869AD30763A8F5BECE28F53D67FC5A75845F0689EF1F78A8  checksums.sha256
```

Exported files in `data/exports/`:
- `csv/carriers.csv`
- `csv/shipments.csv`
- `csv/invoices.csv`
- `csv/invoice_lines.csv`
- `csv/ground_truth_labels.csv`
- `json/master_carrier_rates.json`
- `json/invoices_reconciled.json`
- `sql/seed_data.sql`

---

## 8. Docker Deployment

Deploy with Docker Compose:
```bash
docker compose up --build
```
Access the application at `http://localhost:8000`.

---

## 9. Documentation Directory

- [Data Dictionary](file:///c:/PROJECTS/FREIGHT%20INVOICE%20VALIDATION%20SYSTEM/docs/data_dictionary.md): Comprehensive schema, entity relationships, and column definitions.
- [System Architecture](file:///c:/PROJECTS/FREIGHT%20INVOICE%20VALIDATION SYSTEM/docs/architecture.md): Rating formulas, negative scenarios logic, and lifecycle diagrams.
- [Source Code Manifest](file:///c:/PROJECTS/FREIGHT%20INVOICE%20VALIDATION%20SYSTEM/docs/source_manifest.md): Complete index of all implemented source files.
- [Validation Report](file:///c:/PROJECTS/FREIGHT%20INVOICE%20VALIDATION%20SYSTEM/docs/validation_report.md): Benchmark metrics, confusion matrix, and financial impact.
