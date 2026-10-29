# Dashboard Screenshots & UI Guide

This directory documents the visual architecture and operational views of the interactive **Freight Invoice Validation System Operations Dashboard** (React 19 + TypeScript + Vite + Tailwind CSS).

---

## Operations Dashboard Views

The frontend application serves 6 dedicated operational views:

### 1. Executive KPIs View (`/`)
- Summary cards: Total Audited Invoices, Clean Matches, Flagged Exceptions, Total Disputed USD, and Recovery Rate.
- High-level charts: Invoice Status Breakdown, Carrier Volume Share, Discrepancy Trend by Carrier.

### 2. Invoice Explorer & Line-Item Drawer
- Paginated and filterable table displaying carrier code, raw shipment reference, invoice date, billed total, expected total, variance, and validation status pill.
- Interactive slide-out drawer providing line-by-line charge reconciliation, contractual tariff references, and diagnostic explanations.

### 3. Exception Triage Queue
- Centralized exception workbench filtering by severity (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `INFO`) and status (`OPEN`, `UNDER_REVIEW`, `APPROVED`, `REJECTED`, `RESOLVED`).
- One-click workflow action buttons to assign auditors, approve disputes, reject frivolous claims, or record manual overrides.

### 4. Credit Note Reconciliation Manager
- Direct reconciliation workbench tracking carrier-issued credit notes against disputed invoice balances.
- Real-time enforcement of remaining dispute balance limits (rejects over-credit submissions exceeding the unrecovered balance).

### 5. Ground-Truth Evaluation Matrix
- Independent benchmark analytics dashboard presenting the $2 \times 2$ Confusion Matrix (`TP`, `FP`, `TN`, `FN`).
- Gauges for Precision ($100.0\%$), Recall ($99.98\%$), F1-Score ($99.99\%$), and Financial Recovery Rate ($99.7\%$).
- Breakdown of all 8 mandatory negative anomaly scenarios.

### 6. Data Quality & Manifest Inspector
- Integrity audit dashboard displaying primary key, foreign key, allowed value, and arithmetic verification statuses.
- Multi-format file export links with cryptographic SHA-256 verification hashes.

---

## How to Capture Dashboard Screenshots Locally

To capture screenshots of the running dashboard:

1. **Start the Backend API Server**:
   ```bash
   .\.venv\Scripts\python -m backend.app.cli serve --host 127.0.0.1 --port 8000
   ```

2. **Start the Frontend Development Server**:
   ```bash
   cd frontend
   npm run dev
   ```

3. **Navigate to `http://localhost:5173`** in your browser.
4. Use standard browser screenshot tools (e.g. Chrome DevTools `Ctrl+Shift+P` $\to$ `Capture full size screenshot`) and save PNGs into `docs/screenshots/`.
