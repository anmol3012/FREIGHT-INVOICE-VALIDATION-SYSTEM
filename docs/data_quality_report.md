# Data-Quality and Reproducibility Validation Report

**Execution Timestamp**: `2026-10-29T07:39:37.280199`  
**Overall Status**: `PASSED`  
**Unintentional Data Defects**: `0`  
**Intentional Negative-Test Anomalies**: `2`  

---

## 1. Record Volume by Entity

| Entity Name | Record Count |
| :--- | :--- |
| Carriers | **5** |
| Lanes | **10** |
| Accessorials | **6** |
| RateCards | **21** |
| RateTiers | **84** |
| Shipments | **30** |
| ShipmentLegs | **30** |
| WeightMeasurements | **30** |
| DeliveryEvidence | **30** |
| FreightInvoices | **25** |
| InvoiceLines | **60** |
| DuplicateInvoiceGroups | **1** |
| InvoiceValidationRuns | **25** |
| AuditExceptions | **8** |
| CreditNotes | **3** |
| AuditEvents | **2** |
| EntityStatusHistory | **33** |
| GroundTruthLabels | **25** |

## 2. Data-Quality Stage Results

| Audit Stage | Status | Findings / Metrics |
| :--- | :--- | :--- |
| **Primary Keys** | `PASSED` | records_checked: 428, null_pks: 0, duplicate_pks: 0, pattern_mismatches: 0 |
| **Foreign Keys** | `PASSED` | unintentional_dangling_references: 0, intentional_unmatched_references: 2 |
| **Allowed Values** | `PASSED` | invalid_enums_count: 0 |
| **Date Rules** | `PASSED` | chronological_date_errors: 0 |
| **Arithmetic Reconciliation** | `PASSED` | arithmetic_defects_count: 0 |
| **Duplicate Checks** | `PASSED` | duplicate_invoice_number_violations: 0, duplicate_clusters_detected: 1 |
| **Lifecycle State Machine** | `PASSED` | lifecycle_defects_count: 0 |
| **Ground Truth Coverage** | `PASSED` | total_ground_truth_labels: 25, clean_invoices_labelled: 17, anomalies_labelled: 8 |

## 3. Ground-Truth Anomaly Distribution

Intentional negative-test scenarios injected into the synthetic evaluation dataset:

| Scenario / Issue Type | Injected Count | Handled by Validation Engine |
| :--- | :--- | :--- |
| `UNKNOWN_SHIPMENT_REF` | **2** | Yes (Flagged & Disputed) |
| `EXPIRED_RATE_CARD` | **2** | Yes (Flagged & Disputed) |
| `INCORRECT_WEIGHT_TIER` | **1** | Yes (Flagged & Disputed) |
| `DUPLICATE_FUEL_SURCHARGE` | **1** | Yes (Flagged & Disputed) |
| `DIMENSIONAL_WEIGHT_DISCREPANCY` | **1** | Yes (Flagged & Disputed) |
| `UNAUTHORIZED_ACCESSORIAL` | **1** | Yes (Flagged & Disputed) |

## 4. Defect Audit Log

> [!NOTE]
> Zero unintentional defects detected. 100% relational integrity, chronological dates, and arithmetic reconciliation verified.
