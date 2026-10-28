# Validation Report & Benchmark Evaluation

## 1. Executive Summary

The **Freight Invoice Validation System** was evaluated against independently stored ground-truth anomaly labels generated with the deterministic seed `20261022`.

The test verified detection across all five mandatory negative scenarios, dual-run data determinism, and full relational integrity.

---

## 2. Benchmark Detection Accuracy Metrics

| Metric | Measured Value | Target | Status |
|---|---|---|---|
| **Accuracy** | **98.00%** | > 90% | **PASSED** |
| **Precision** | **100.00%** | > 85% | **PASSED (Zero False Positives)** |
| **Recall (Sensitivity)** | **95.00%** | > 85% | **PASSED** |
| **Specificity** | **100.00%** | > 90% | **PASSED** |
| **F1-Score** | **0.9744** | > 0.85 | **PASSED** |

### Confusion Matrix
- **True Positives (TP)**: 76 (Anomalies correctly detected & disputed)
- **False Positives (FP)**: 0 (Zero false alarms on clean invoices)
- **True Negatives (TN)**: 120 (Clean invoices accurately passed)
- **False Negatives (FN)**: 4 (Boundary margin anomalies)

---

## 3. Negative Scenario Detection Breakdown

| Scenario Code | Description | Injected Count | Detected | Detection Rate (%) |
|---|---|---|---|---|
| `BASE_RATE_MISMATCH` | Linehaul rate markup above contracted tariff | 16 | 16 | **100.0%** |
| `WEIGHT_DISCREPANCY` | Scale vs re-weigh weight discrepancy | 16 | 16 | **100.0%** |
| `UNAUTHORIZED_ACCESSORIAL` | Unrendered liftgate / detention fees | 16 | 16 | **100.0%** |
| `DUPLICATE_BILLING` | Exact fingerprint and repeat BOL billing | 16 | 14 | **87.5%** |
| `INVALID_CREDIT_NOTE` | Excessive or uncontracted credit notes | 16 | 14 | **87.5%** |
| `NORMAL` | Compliant invoices within tolerance | 120 | 120 (Clean) | **100.0% (Specificity)** |

---

## 4. Financial Impact Analysis

- **Total Injected Variance (Leakage)**: \$49,200.02
- **Recovered Variance (Disputed & Protected)**: \$23,805.92
- **Direct Financial Leakage Prevented**: **48.4% of all invoice discrepancies**

---

## 5. Seed Determinism & Integrity Checksums

Two independent full synthesis runs using the fixed seed `20261022` produced identical cryptographic SHA-256 hash checksums across all exported files:

| Exported File | SHA-256 Digest |
|---|---|
| `csv/carriers.csv` | `7e897fe74f0c8643862ffbe9939adcf7896ff6d934bb883ca20fc45f2bf1350a` |
| `csv/shipments.csv` | `b1c1d6d96b165a266a2e2be26ecffbca142d7b87eecb313efbf6d6556e9c6001` |
| `csv/invoices.csv` | `50ecd8818dff418ee4c7be4ec657731bc9d3bfaf64f33b1e35fa3569ee38b255` |
| `csv/invoice_lines.csv` | `0dafae51095fb49ff1daecda1ca58fb3a4d6b63ca04ffdf50907297e65158673` |
| `csv/ground_truth_labels.csv` | `0889e4f09475fcc3f53ae8861d9be85a9dfda95fb194911d87e0ce05fbc3075d` |
| `json/master_carrier_rates.json` | `0712fb4981d12f74136208a543666249ec1bc541ebc9693cf837905b76c8c199` |
| `json/invoices_reconciled.json` | `eef0479b3903668db7f89bfa816dc0ce872a095111979ca6f53a7a92cfb373cf` |
| `sql/seed_data.sql` | `0ba9d0eb45a0d0efef7cb7ce394c86127e4e1a067ca67fe7bc042217c09d5757` |
| **Combined Manifest (`checksums.sha256`)** | `37432DDC69EF50BE869AD30763A8F5BECE28F53D67FC5A75845F0689EF1F78A8` |

**Verification**: `data/exports_run1` $\equiv$ `data/exports_run2` (Match: 100%).
