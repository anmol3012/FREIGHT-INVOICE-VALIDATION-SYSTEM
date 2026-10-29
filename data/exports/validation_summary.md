# Data-Quality and Reproducibility Validation Report

**Execution Timestamp**: `2026-10-29T05:12:30.589964`  
**Overall Status**: `PASSED`  
**Unintentional Data Defects**: `0`  
**Intentional Negative-Test Anomalies**: `10`  

---

## 1. Record Volume by Entity

| Entity Name | Record Count |
| :--- | :--- |
| Carriers | **20** |
| Lanes | **45** |
| Accessorials | **6** |
| RateCards | **66** |
| RateTiers | **264** |
| Shipments | **250** |
| ShipmentLegs | **250** |
| WeightMeasurements | **250** |
| DeliveryEvidence | **250** |
| FreightInvoices | **200** |
| InvoiceLines | **516** |
| DuplicateInvoiceGroups | **10** |
| InvoiceValidationRuns | **600** |
| AuditExceptions | **60** |
| CreditNotes | **18** |
| AuditEvents | **399** |
| EntityStatusHistory | **92** |
| GroundTruthLabels | **200** |

## 2. Data-Quality Stage Results

| Audit Stage | Status | Findings / Metrics |
| :--- | :--- | :--- |
| **Primary Keys** | `PASSED` | records_checked: 3496, null_pks: 0, duplicate_pks: 0, pattern_mismatches: 0 |
| **Foreign Keys** | `PASSED` | unintentional_dangling_references: 0, intentional_unmatched_references: 10 |
| **Allowed Values** | `PASSED` | invalid_enums_count: 0 |
| **Date Rules** | `PASSED` | chronological_date_errors: 0 |
| **Arithmetic Reconciliation** | `PASSED` | arithmetic_defects_count: 0 |
| **Duplicate Checks** | `PASSED` | duplicate_invoice_number_violations: 0, duplicate_clusters_detected: 10 |
| **Lifecycle State Machine** | `PASSED` | lifecycle_defects_count: 0 |
| **Ground Truth Coverage** | `PASSED` | total_ground_truth_labels: 200, clean_invoices_labelled: 140, anomalies_labelled: 60 |

## 3. Ground-Truth Anomaly Distribution

Intentional negative-test scenarios injected into the synthetic evaluation dataset:

| Scenario / Issue Type | Injected Count | Handled by Validation Engine |
| :--- | :--- | :--- |
| `UNKNOWN_SHIPMENT_REF` | **10** | Yes (Flagged & Disputed) |
| `EXPIRED_RATE_CARD` | **10** | Yes (Flagged & Disputed) |
| `INCORRECT_WEIGHT_TIER` | **10** | Yes (Flagged & Disputed) |
| `DUPLICATE_FUEL_SURCHARGE` | **10** | Yes (Flagged & Disputed) |
| `DIMENSIONAL_WEIGHT_DISCREPANCY` | **10** | Yes (Flagged & Disputed) |
| `UNAUTHORIZED_ACCESSORIAL` | **10** | Yes (Flagged & Disputed) |

## 4. Defect Audit Log

> [!NOTE]
> Zero unintentional defects detected. 100% relational integrity, chronological dates, and arithmetic reconciliation verified.
