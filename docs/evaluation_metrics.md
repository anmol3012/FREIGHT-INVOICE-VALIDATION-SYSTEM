# Evaluation Metrics and Ground-Truth Separation Framework

This document details the mathematical definitions, evaluation methodology, and architectural safeguards used to evaluate the audit detection performance of the **Freight Invoice Validation System**.

---

## 1. Units of Evaluation

To ensure statistical integrity and avoid metric distortion, the evaluation framework distinguishes three distinct units of evaluation:

1. **Invoice-Level Evaluation**: Measures the binary classification capability of the audit engine to correctly classify an overall invoice as either `VALID` (clean contractual match) or `ANOMALOUS` (contains one or more discrepancies requiring human review / dispute).
2. **Exception-Level Evaluation**: Measures itemized detection granularity (e.g. rate mismatch, volumetric discrepancy, unauthorized accessorial, duplicate surcharge).
3. **Financial Impact Evaluation**: Quantifies dollar-denominated variance recovery rates, approved credit value, and overcharge protection.

These units are evaluated independently and are never mixed within a single metric.

---

## 2. Mathematical Definitions and Formulas

### Confusion Matrix (Invoice-Level Classification)

Given a population of $N$ audited invoices with ground-truth labels:

| Metric | Code | Mathematical Meaning | Operational Meaning |
|---|---|---|---|
| **True Positive** | **TP** | $\text{Actual} = \text{FAIL} \land \text{Predicted} = \text{FAIL}$ | Anomalous invoice correctly identified and disputed |
| **False Positive** | **FP** | $\text{Actual} = \text{PASS} \land \text{Predicted} = \text{FAIL}$ | Clean baseline invoice falsely flagged with exceptions |
| **True Negative** | **TN** | $\text{Actual} = \text{PASS} \land \text{Predicted} = \text{PASS}$ | Clean baseline invoice correctly validated and approved |
| **False Negative** | **FN** | $\text{Actual} = \text{FAIL} \land \text{Predicted} = \text{PASS}$ | Billed anomaly missed by the validation engine (leakage) |

---

### Classification Metrics

#### 1. Accuracy
Measures overall correctness across both clean and anomalous invoices:
$$\text{Accuracy} = \frac{TP + TN}{TP + TN + FP + FN}$$

#### 2. Precision (Positive Predictive Value)
Measures the proportion of disputed invoices that were genuine anomalies:
$$\text{Precision} = \frac{TP}{TP + FP}$$

#### 3. Recall (Sensitivity / True Positive Rate)
Measures the proportion of injected anomalies successfully detected by the engine:
$$\text{Recall} = \frac{TP}{TP + FN}$$

#### 4. Specificity (True Negative Rate)
Measures the ability of the engine to correctly accept clean baseline invoices without false alarms:
$$\text{Specificity} = \frac{TN}{TN + FP}$$

#### 5. F1-Score
The harmonic mean of Precision and Recall:
$$F_1 = 2 \times \frac{\text{Precision} \times \text{Recall}}{\text{Precision} + \text{Recall}} = \frac{2 \times TP}{2 \times TP + FP + FN}$$

---

### Zero-Denominator Conventions

When a metric denominator evaluates to zero (for example, in a test dataset containing zero anomalies or zero clean invoices), the framework applies the following documented conventions:

- If $TP + FP = 0$: $\text{Precision} = 0.0$
- If $TP + FN = 0$: $\text{Recall} = 0.0$
- If $TN + FP = 0$: $\text{Specificity} = 0.0$
- If $\text{Precision} + \text{Recall} = 0$: $F_1 = 0.0$
- If total sample count $N = 0$: $\text{Accuracy} = 0.0$

---

### Financial Recovery Metrics

#### 1. Financial Recovery Rate
Quantifies the percentage of injected overbilling dollars successfully stopped:
$$\text{Recovery Rate (\%)} = \frac{\text{Total Detected Overbilling (USD)}}{\text{Total Injected Overbilling (USD)}} \times 100$$

#### 2. Credit Note Protection (Scenario E)
- **Approved Credit Value**: Total dollar amount of credit notes matching valid dispute balances.
- **Rejected Credit Value**: Total dollar amount of invalid or excessive credit notes prevented from reducing dispute balances.

---

## 3. Negative Scenario Detection Taxonomy

The framework evaluates detection performance across all 8 documented anomaly scenarios:

| Scenario Code | Classification | Expected Verdict | Primary Detection Mechanism |
|---|---|---|---|
| `NORMAL` | Baseline Clean | `PASS` | Linehaul, fuel surcharge, and accessorial formulas match within $\$0.05$ |
| `UNKNOWN_SHIPMENT_REF` | Scenario A | `FAIL` | Master shipment reference lookup fails; reference quarantined |
| `EXPIRED_RATE_CARD` | Scenario B | `FAIL` | Contract validity window expired before shipment date |
| `INCORRECT_WEIGHT_TIER` | Scenario C | `FAIL` | Applied unit rate differs from contract weight tier bracket |
| `DUPLICATE_FUEL_SURCHARGE` | Scenario D | `FAIL` | Secondary fuel surcharge line detected on same shipment |
| `EXCESSIVE_CREDIT_NOTE` | Scenario E | `FAIL` (Credit Note) | Credit amount exceeds remaining approved disputed balance |
| `DIMENSIONAL_WEIGHT_DISCREPANCY`| Scenario F | `FAIL` | Billed chargeable weight exceeds certified origin scale density |
| `UNAUTHORIZED_ACCESSORIAL` | Scenario G | `FAIL` | Liftgate/detention billed without required delivery proof |
| `DUPLICATE_INVOICE` | Scenario H | `FAIL` | Exact invoice number or duplicate fingerprint hash match |

---

## 4. Ground-Truth Separation and Leakage Prevention

To guarantee independent, unbiased evaluation:

1. **Physical and Schema Separation**:
   - Operational calculation and validation tables (`freight_invoices`, `invoice_lines`, `rate_cards`, `shipments`) have no foreign keys or references to `ground_truth_labels`.
   - The operational validation engine (`backend/app/engine/validator.py`, `calculator.py`, `contract_selector.py`, `weight_service.py`, `accessorial_service.py`, `duplicate_service.py`, `credit_note_service.py`) does not import or read `GroundTruthLabel` or ground-truth export files.
2. **Post-Hoc Evaluation Execution**:
   - The evaluation module (`backend/app/engine/evaluator.py`) executes strictly **after** validation decisions and exceptions have been persisted to the database.
3. **Automated Leakage Test**:
   - `tests/test_ground_truth_leakage.py` uses Python Abstract Syntax Tree (AST) analysis and inspection to verify that no engine module imports or references ground truth models or files.
