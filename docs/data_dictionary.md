# Data Dictionary: Freight Invoice Validation System

This document specifies the schema, constraints, data types, and business semantics of all entities modeled in the Freight Invoice Validation System.

---

## 1. Master Data Entities

### 1.1 `carriers`
Represents transportation service providers with contractual relationships.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `id` | INTEGER | No | Primary Key. |
| `carrier_code` | VARCHAR(10) | No | Standard Carrier Alpha Code (SCAC), unique index (e.g. `ODFL`, `FXFE`). |
| `name` | VARCHAR(100) | No | Registered legal company name. |
| `tax_id` | VARCHAR(30) | No | Federal Employer Identification Number (FEIN). |
| `payment_terms_days` | INTEGER | No | Contracted net payment term days (e.g. 15, 30, 45). |
| `status` | VARCHAR(20) | No | Account status (`ACTIVE`, `SUSPENDED`). |
| `contact_email` | VARCHAR(100) | Yes | Remittance and billing contact email. |
| `created_at` | DATETIME | No | Record creation timestamp. |

### 1.2 `rate_cards`
Defines contracted rating rules, effective dates, and fuel baselines for a carrier.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `id` | INTEGER | No | Primary Key. |
| `rate_card_code` | VARCHAR(50) | No | Unique contractual schedule identifier. |
| `carrier_id` | INTEGER | No | Foreign key referencing `carriers.id`. |
| `effective_date` | DATE | No | Date contract rates take effect. |
| `expiration_date` | DATE | No | Contract expiration date. |
| `currency` | VARCHAR(3) | No | ISO currency code (default `USD`). |
| `base_rate_model` | VARCHAR(20) | No | Rating model (`PER_CWT`, `PER_MILE`, `FLAT`). |
| `minimum_charge_floor` | FLOAT | No | Absolute floor charge for any shipment leg. |
| `fuel_base_price` | FLOAT | No | Baseline DOE diesel peg (e.g. $3.00/gal). |
| `fuel_surcharge_pct_per_interval` | FLOAT | No | FSC percentage step per $0.05 index move (e.g. 0.005). |
| `status` | VARCHAR(20) | No | Status (`ACTIVE`, `EXPIRED`, `SUPERSEDED`). |

### 1.3 `rate_lanes`
Geographic transit lanes and contracted baseline rates.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `id` | INTEGER | No | Primary Key. |
| `rate_card_id` | INTEGER | No | Foreign key referencing `rate_cards.id`. |
| `origin_zip_prefix` | VARCHAR(5) | No | 3-digit postal prefix or `ALL`. |
| `dest_zip_prefix` | VARCHAR(5) | No | 3-digit postal prefix or `ALL`. |
| `origin_region` | VARCHAR(50) | Yes | Origin freight territory. |
| `dest_region` | VARCHAR(50) | Yes | Destination freight territory. |
| `base_rate_cwt` | FLOAT | No | Contracted rate per hundredweight ($/CWT). |
| `base_rate_per_mile` | FLOAT | No | Contracted rate per road mile ($/mi). |
| `flat_rate` | FLOAT | No | Flat charge for lane if applicable. |
| `minimum_charge` | FLOAT | No | Lane minimum charge floor. |
| `transit_days` | INTEGER | No | Standard contractual transit days. |

### 1.4 `accessorial_rules`
Contracted terms for secondary logistics services.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `id` | INTEGER | No | Primary Key. |
| `carrier_id` | INTEGER | No | Foreign key referencing `carriers.id`. |
| `code` | VARCHAR(30) | No | Accessorial charge code (`LIFTGATE`, `DETENTION`, `RESIDENTIAL`, `INSIDE_DELIVERY`, `HAZMAT`, `APPOINTMENT`). |
| `name` | VARCHAR(100) | No | Human-readable accessorial service name. |
| `rate_type` | VARCHAR(20) | No | Rating type (`FLAT`, `PER_HOUR`, `PER_CWT`, `PERCENTAGE`). |
| `unit_rate` | FLOAT | No | Contracted fee amount per unit. |
| `free_time_minutes` | INTEGER | No | Free dwell time before detention commences (e.g. 120). |
| `proof_required` | BOOLEAN | No | Whether delivery proof or GPS timestamp is mandatory. |

---

## 2. Operational Logistics Entities

### 2.1 `shipments`
Physical transport movements executed under a Bill of Lading.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `id` | INTEGER | No | Primary Key. |
| `bol_number` | VARCHAR(50) | No | Unique Bill of Lading number. |
| `carrier_id` | INTEGER | No | Foreign key referencing `carriers.id`. |
| `origin_zip` | VARCHAR(10) | No | Origin postal code. |
| `origin_city` | VARCHAR(50) | No | Origin city name. |
| `origin_state` | VARCHAR(10) | No | Origin state code. |
| `destination_zip` | VARCHAR(10) | No | Destination postal code. |
| `destination_city` | VARCHAR(50) | No | Destination city name. |
| `destination_state` | VARCHAR(10) | No | Destination state code. |
| `pickup_date` | DATE | No | Actual cargo pickup date. |
| `delivery_date` | DATE | No | Actual cargo delivery date. |
| `distance_miles` | FLOAT | No | Road mileage between origin and destination. |
| `current_fuel_index` | FLOAT | No | DOE diesel index price at time of pickup. |
| `dock_type` | VARCHAR(30) | No | Destination facility type (`STANDARD_DOCK`, `GROUND_LEVEL`, `RESIDENTIAL`). |
| `status` | VARCHAR(20) | No | Shipment state (`DELIVERED`, `IN_TRANSIT`, `CANCELLED`). |

### 2.2 `weight_measurements`
Certified weight certificates and dimensional calculations.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `id` | INTEGER | No | Primary Key. |
| `shipment_id` | INTEGER | No | Foreign key referencing `shipments.id`. |
| `measurement_type` | VARCHAR(30) | No | Source (`ORIGIN_SCALE`, `CARRIER_REWEIGH`, `DIMENSIONAL`). |
| `gross_weight_lbs` | FLOAT | No | Scale gross cargo weight in pounds. |
| `length_in` | FLOAT | No | Length in inches. |
| `width_in` | FLOAT | No | Width in inches. |
| `height_in` | FLOAT | No | Height in inches. |
| `dim_factor` | FLOAT | No | Dimensional freight factor (standard 139 cu in/lb). |
| `billable_weight_lbs` | FLOAT | No | Calculated: $\max(\text{gross weight}, \frac{L \times W \times H}{139})$. |
| `certified` | BOOLEAN | No | Official certified scale slip flag. |

### 2.3 `delivery_records`
Official Proof of Delivery (POD) signed by the consignee.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `id` | INTEGER | No | Primary Key. |
| `shipment_id` | INTEGER | No | Foreign key referencing `shipments.id`. |
| `delivered_at` | DATETIME | No | Consignee acceptance timestamp. |
| `recipient_name` | VARCHAR(100) | No | Name of receiving dock agent. |
| `signed_pod_ref` | VARCHAR(100) | Yes | Digital POD document signature reference. |
| `facility_dock_type` | VARCHAR(50) | No | Confirmed dock configuration. |
| `liftgate_actually_used`| BOOLEAN | No | Physical proof whether hydraulic liftgate was deployed. |
| `detention_minutes_recorded` | INTEGER | No | GPS/ELD tracked facility dwell time in minutes. |

---

## 3. Financial Invoicing & Exception Entities

### 3.1 `invoices`
Carrier invoice headers submitted for freight settlement.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `id` | INTEGER | No | Primary Key. |
| `invoice_number` | VARCHAR(50) | No | Unique carrier invoice number. |
| `carrier_id` | INTEGER | No | Foreign key referencing `carriers.id`. |
| `shipment_id` | INTEGER | Yes | Foreign key referencing `shipments.id`. |
| `bol_number_billed` | VARCHAR(50) | No | Bill of Lading cited by carrier. |
| `invoice_date` | DATE | No | Date of billing. |
| `due_date` | DATE | No | Net payment due date. |
| `currency` | VARCHAR(3) | No | ISO currency code. |
| `total_billed_amount` | FLOAT | No | Total billed amount submitted by carrier. |
| `calculated_expected_amount` | FLOAT | No | Total contractual amount calculated by system engine. |
| `total_variance_amount` | FLOAT | No | Net financial variance ($\text{billed} - \text{expected}$). |
| `status` | VARCHAR(30) | No | Lifecycle status (`PENDING_AUDIT`, `VALIDATED_MATCH`, `EXCEPTION_DISPUTED`, `EXCEPTION_APPROVED`, `PAID`, `REJECTED`). |
| `validation_status` | VARCHAR(30) | No | Audit outcome (`PASSED`, `FAILED`, `UNAUDITED`). |
| `is_duplicate` | BOOLEAN | No | Flag indicating duplicate billing. |
| `duplicate_of_invoice_id` | INTEGER | Yes | Foreign key to original invoice if duplicate. |
| `fingerprint_hash` | VARCHAR(64) | Yes | SHA-256 fingerprint `(carrier_id:bol:billed_amount)`. |

### 3.2 `invoice_lines`
Itemized line-item charges on the invoice.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `id` | INTEGER | No | Primary Key. |
| `invoice_id` | INTEGER | No | Foreign key referencing `invoices.id`. |
| `line_number` | INTEGER | No | Sequential line number on invoice. |
| `charge_type` | VARCHAR(30) | No | Category (`LINEHAUL`, `FUEL_SURCHARGE`, `ACCESSORIAL`, `MISC`). |
| `charge_code` | VARCHAR(30) | Yes | Contractual code (`LH`, `FSC`, `LIFTGATE`, `DETENTION`). |
| `description` | VARCHAR(200) | No | Carrier charge description. |
| `billed_units` | FLOAT | No | Billed quantity (e.g. CWT, miles, hours). |
| `billed_rate` | FLOAT | No | Billed rate per unit. |
| `billed_amount` | FLOAT | No | Total billed for line. |
| `expected_units` | FLOAT | No | Contractually verified units. |
| `expected_rate` | FLOAT | No | Contracted rate card rate. |
| `expected_amount` | FLOAT | No | Contractual expected line charge. |
| `variance_amount` | FLOAT | No | Variance on line ($\text{billed} - \text{expected}$). |
| `status` | VARCHAR(30) | No | Line audit status (`MATCH`, `VARIANCE_DISCREPANCY`, `UNAUTHORIZED`). |
| `discrepancy_reason` | VARCHAR(255) | Yes | Human-readable root cause explanation. |

### 3.3 `invoice_exceptions`
Discrepancy tickets generated when billed charges deviate outside tolerance.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `id` | INTEGER | No | Primary Key. |
| `invoice_id` | INTEGER | No | Foreign key referencing `invoices.id`. |
| `invoice_line_id` | INTEGER | Yes | Foreign key referencing `invoice_lines.id`. |
| `category` | VARCHAR(50) | No | Negative scenario code (`BASE_RATE_MISMATCH`, `WEIGHT_DISCREPANCY`, `UNAUTHORIZED_ACCESSORIAL`, `DUPLICATE_BILLING`, `INVALID_CREDIT_NOTE`). |
| `severity` | VARCHAR(20) | No | Severity level (`INFO`, `WARNING`, `CRITICAL`). |
| `billed_amount` | FLOAT | No | Erroneous billed amount. |
| `expected_amount` | FLOAT | No | Valid contractual amount. |
| `variance_amount` | FLOAT | No | Amount in dispute. |
| `status` | VARCHAR(30) | No | Status (`OPEN`, `UNDER_REVIEW`, `APPROVED_OVERRIDE`, `DISPUTED`, `AUTO_RESOLVED`). |
| `root_cause_code` | VARCHAR(50) | No | Machine-readable diagnosis code. |
| `explanation` | TEXT | No | Full contextual justification. |

---

## 4. Dispute, Credit & Audit Entities

### 4.1 `credit_notes`
Carrier credit notes issued to resolve billing discrepancies.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `id` | INTEGER | No | Primary Key. |
| `credit_note_number` | VARCHAR(50) | No | Carrier credit document reference. |
| `carrier_id` | INTEGER | No | Foreign key referencing `carriers.id`. |
| `original_invoice_id` | INTEGER | No | Foreign key referencing disputed `invoices.id`. |
| `issue_date` | DATE | No | Credit note date. |
| `credit_amount` | FLOAT | No | Total credit balance offered. |
| `applied_amount` | FLOAT | No | Credit balance reconciled and applied. |
| `remaining_balance` | FLOAT | No | Remaining unapplied credit. |
| `status` | VARCHAR(30) | No | Status (`UNAPPLIED`, `PARTIALLY_APPLIED`, `FULLY_APPLIED`, `REJECTED`). |
| `reason_code` | VARCHAR(50) | No | Reason (`RATE_CORRECTION`, `WEIGHT_ADJUSTMENT`, etc.). |
| `rejection_reason` | TEXT | Yes | Explanation if credit note was rejected (e.g. excessive amount). |

### 4.2 `audit_events`
Immutable write-only audit trail logging all lifecycle actions.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `id` | INTEGER | No | Primary Key. |
| `entity_type` | VARCHAR(50) | No | Target entity (`INVOICE`, `EXCEPTION`, `CREDIT_NOTE`, `SYSTEM`). |
| `entity_id` | VARCHAR(50) | No | Identifier of the affected entity. |
| `event_type` | VARCHAR(50) | No | Action type (`VALIDATION_RUN`, `DUPLICATE_DETECTED`, `CREDIT_APPLIED`, `MANUAL_OVERRIDE`). |
| `actor` | VARCHAR(50) | No | Actor responsible (`SYSTEM_AUDITOR`, `OPERATOR_DASHBOARD`, `DATA_GENERATOR`). |
| `payload_json` | TEXT | Yes | JSON snapshot of parameters or state delta. |
| `notes` | VARCHAR(255) | Yes | Summary notes. |
| `timestamp` | DATETIME | No | High-precision audit timestamp. |

### 4.3 `ground_truth_labels`
Independently stored synthetic truth labels for audit accuracy benchmarking.

| Column | Type | Nullable | Description |
|---|---|---|---|
| `id` | INTEGER | No | Primary Key. |
| `invoice_id` | INTEGER | Yes | Linked invoice ID. |
| `invoice_number` | VARCHAR(50) | No | Invoice number. |
| `bol_number` | VARCHAR(50) | No | BOL number. |
| `carrier_code` | VARCHAR(10) | No | Carrier code. |
| `scenario_type` | VARCHAR(50) | No | Injected scenario (`NORMAL`, `BASE_RATE_MISMATCH`, `WEIGHT_DISCREPANCY`, `UNAUTHORIZED_ACCESSORIAL`, `DUPLICATE_BILLING`, `INVALID_CREDIT_NOTE`). |
| `is_anomaly` | BOOLEAN | No | True if invoice was manipulated with an anomaly. |
| `expected_verdict` | VARCHAR(20) | No | Correct expected audit result (`PASS`, `FAIL`). |
| `ground_truth_billed` | FLOAT | No | Synthetic billed amount. |
| `ground_truth_expected`| FLOAT | No | Pure contractual expected amount. |
| `injected_variance` | FLOAT | No | Variance introduced during generation. |
| `anomaly_details_json`| TEXT | Yes | Generation parameter details. |
