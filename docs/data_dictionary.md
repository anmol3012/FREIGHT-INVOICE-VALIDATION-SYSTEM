# Data Dictionary: Freight Invoice Validation System (Phase 1)

This comprehensive Data Dictionary specifies the complete relational schema, field definitions, primary/foreign key constraints, measurement units, enumerations, validation rules, and data classifications for the Freight Invoice Validation System.

---

## 1. Table Inventory

| Entity Name | Table Name | Type | Description |
|---|---|---|---|
| **Carrier** | `carriers` | Core Entity | Transportation service providers with contractual relationships |
| **RateCard** | `rate_cards` | Core Entity | Contracted tariff schedules on carrier-lane-service combinations |
| **RateTier** | `rate_tiers` | Supporting Entity | Weight-break tier pricing intervals for RateCards |
| **Lane** | `lanes` | Core Entity | Geographic origin/destination transport lanes with road distances |
| **Shipment** | `shipments` | Core Entity | Physical freight movements executed under a Bill of Lading |
| **ShipmentLeg** | `shipment_legs` | Core Entity | Multi-modal sequential transport legs of a shipment |
| **WeightMeasurement** | `weight_measurements`| Core Entity | Certified scale slips and cubic dimensional measurements |
| **Accessorial** | `accessorials` | Core Entity | Contracted secondary logistics service fee definitions |
| **ShipmentAccessorial**| `shipment_accessorials`| Supporting Bridge| N:M assignment bridge for accessorial events on shipments |
| **DeliveryEvidence** | `delivery_evidence` | Supporting Entity| Consignee Proof of Delivery (POD) & facility dock proof |
| **FreightInvoice** | `freight_invoices` | Core Entity | Carrier billing headers with untrusted reference staging |
| **InvoiceLine** | `invoice_lines` | Core Entity | Itemized line charges reconciled against contractual rating |
| **AuditException** | `audit_exceptions` | Core Entity | Actionable discrepancy tickets flagged by the audit engine |
| **CreditNote** | `credit_notes` | Core Entity | Carrier credit adjustments applied to resolve invoice exceptions |
| **DuplicateInvoiceGroup**| `duplicate_invoice_groups`| Supporting Entity| Clusters of duplicate invoices tracked by SHA-256 fingerprints |
| **InvoiceValidationRun**| `invoice_validation_runs`| Supporting Entity| Audit engine execution log per invoice |
| **AuditEvent** | `audit_events` | Supporting Entity| Immutable operational event log preserving state changes |
| **EntityStatusHistory**| `entity_status_history`| Supporting Entity| Explicit lifecycle state progression audit history |

---

## 2. Comprehensive Field Specifications

### 2.1 `carriers`
*Primary Key*: `carrier_id` (e.g. `CAR-000001`)

| Field Name | Business Meaning | DB Type | Status | Default | Allowed Values / Enum | Units | Constraints | Data Classification | Lifecycle Context |
|---|---|---|---|---|---|---|---|---|---|
| `carrier_id` | Immutable carrier ID | VARCHAR(30) | Required | None | `CAR-[0-9]{6}` | None | PK, Indexed | Source | Operational |
| `carrier_name` | Legal entity name | VARCHAR(100) | Required | None | Valid string | None | NOT NULL | Source | Operational |
| `carrier_code` | SCAC identifier | VARCHAR(10) | Required | None | 2-4 letter alpha | None | Unique, Indexed | Source | Operational |
| `status` | Operational status | VARCHAR(20) | Required | `ACTIVE` | `CarrierStatus` (ACTIVE, SUSPENDED, INACTIVE) | None | NOT NULL | Operational | Operational |
| `country_code`| Headquarters country | VARCHAR(3) | Required | `USA` | ISO 3166-1 alpha-3 | None | NOT NULL | Source | Operational |
| `created_at` | Record creation time | DATETIME | Required | `utcnow()` | Valid timestamp | UTC | NOT NULL | System | Historical |
| `updated_at` | Last updated time | DATETIME | Required | `utcnow()` | Valid timestamp | UTC | NOT NULL | System | Historical |

---

### 2.2 `lanes`
*Primary Key*: `lane_id` (e.g. `LANE-000001`)

| Field Name | Business Meaning | DB Type | Status | Default | Allowed Values / Enum | Units | Constraints | Data Classification | Lifecycle Context |
|---|---|---|---|---|---|---|---|---|---|
| `lane_id` | Immutable lane ID | VARCHAR(30) | Required | None | `LANE-[0-9]{6}` | None | PK, Indexed | Source | Operational |
| `origin_location_code` | Origin facility/hub code | VARCHAR(20) | Required | None | Valid code (e.g. ATL-01) | None | Indexed, NOT NULL | Source | Operational |
| `destination_location_code` | Destination facility code | VARCHAR(20) | Required | None | Valid code (e.g. ORD-01) | None | Indexed, NOT NULL | Source | Operational |
| `origin_city` | Origin city name | VARCHAR(50) | Required | None | Valid city | None | NOT NULL | Source | Operational |
| `destination_city` | Destination city name | VARCHAR(50) | Required | None | Valid city | None | NOT NULL | Source | Operational |
| `origin_country` | Origin country | VARCHAR(3) | Required | `USA` | ISO 3166-1 alpha-3 | None | NOT NULL | Source | Operational |
| `destination_country`| Destination country | VARCHAR(3) | Required | `USA` | ISO 3166-1 alpha-3 | None | NOT NULL | Source | Operational |
| `distance_km` | Transit road distance | FLOAT | Required | None | Value > 0 | Kilometers | `CHECK(distance_km > 0)` | Operational | Operational |
| `status` | Lane active status | VARCHAR(20) | Required | `ACTIVE` | `LaneStatus` (ACTIVE, INACTIVE) | None | NOT NULL | Operational | Operational |

---

### 2.3 `rate_cards`
*Primary Key*: `rate_card_id` (e.g. `RATE-CAR-000001-2026-01`)

| Field Name | Business Meaning | DB Type | Status | Default | Allowed Values / Enum | Units | Constraints | Data Classification | Lifecycle Context |
|---|---|---|---|---|---|---|---|---|---|
| `rate_card_id` | Immutable tariff ID | VARCHAR(50) | Required | None | `RATE-{carrier}-{year}-{seq}` | None | PK, Indexed | Source | Operational |
| `carrier_id` | Carrier reference | VARCHAR(30) | Required | None | Valid `carrier_id` | None | FK (`carriers`), Indexed | Source | Operational |
| `lane_id` | Lane reference | VARCHAR(30) | Required | None | Valid `lane_id` | None | FK (`lanes`), Indexed | Source | Operational |
| `service_level`| Transit service tier | VARCHAR(20) | Required | `STANDARD` | `ServiceLevel` (STANDARD, EXPEDITED, OVERNIGHT, ECONOMY) | None | NOT NULL | Source | Operational |
| `currency` | Contract currency | VARCHAR(3) | Required | `USD` | ISO 4217 code | None | NOT NULL | Source | Operational |
| `effective_from`| Contract start date | DATE | Required | None | Valid date | Date | NOT NULL, Indexed | Source | Operational |
| `effective_to` | Contract end date (inclusive)| DATE | Optional | `NULL` | Valid date >= effective_from | Date | Indexed, NULL = open-ended | Source | Operational |
| `base_rate` | Base flat charge | FLOAT | Required | None | Value >= 0 | Currency ($) | `CHECK(base_rate >= 0)` | Source | Operational |
| `minimum_charge`| Minimum charge floor | FLOAT | Required | None | Value >= 0 | Currency ($) | `CHECK(minimum_charge >= 0)` | Source | Operational |
| `dimensional_weight_divisor` | Metric volumetric factor | FLOAT | Required | 5000.0 | Value > 0 (std: 5000) | $cm^3/kg$ | `CHECK(divisor > 0)` | Source | Operational |
| `status` | Contract status | VARCHAR(20) | Required | `ACTIVE` | `RateCardStatus` (ACTIVE, EXPIRED, SUPERSEDED, DRAFT) | None | NOT NULL | Operational | Operational |
| `created_at` | Record creation time | DATETIME | Required | `utcnow()` | Valid timestamp | UTC | NOT NULL | System | Historical |

---

### 2.4 `rate_tiers`
*Primary Key*: `rate_tier_id` (e.g. `TIER-RATE-CAR-000001-2026-01-01`)

| Field Name | Business Meaning | DB Type | Status | Default | Allowed Values / Enum | Units | Constraints | Data Classification | Lifecycle Context |
|---|---|---|---|---|---|---|---|---|---|
| `rate_tier_id` | Immutable tier ID | VARCHAR(60) | Required | None | `TIER-{rate_card_id}-{seq}` | None | PK, Indexed | Source | Operational |
| `rate_card_id` | Parent rate card | VARCHAR(50) | Required | None | Valid `rate_card_id` | None | FK (`rate_cards`), Indexed | Source | Operational |
| `tier_sequence`| Sequence position | INTEGER | Required | None | Value >= 1 | Sequence | Unique per rate card | Source | Operational |
| `min_weight_kg`| Minimum tier weight | FLOAT | Required | None | Value >= 0 | Kilograms | `CHECK(min_weight_kg >= 0)` | Source | Operational |
| `max_weight_kg`| Maximum tier weight | FLOAT | Optional | `NULL` | Value > min_weight_kg | Kilograms | `CHECK(max > min)` | Source | Operational |
| `rate_per_kg` | Rate per kg in tier | FLOAT | Required | None | Value >= 0 | \$/kg | `CHECK(rate_per_kg >= 0)` | Source | Operational |
| `flat_surcharge`| Tier baseline fee | FLOAT | Required | 0.0 | Value >= 0 | Currency ($) | `CHECK(flat_surcharge >= 0)` | Source | Operational |
| `created_at` | Record creation time | DATETIME | Required | `utcnow()` | Valid timestamp | UTC | NOT NULL | System | Historical |

---

### 2.5 `shipments`
*Primary Key*: `shipment_id` (e.g. `SHP-2026-000001`)

| Field Name | Business Meaning | DB Type | Status | Default | Allowed Values / Enum | Units | Constraints | Data Classification | Lifecycle Context |
|---|---|---|---|---|---|---|---|---|---|
| `shipment_id` | Unique shipment BOL | VARCHAR(30) | Required | None | `SHP-{year}-{seq}` | None | PK, Indexed | Source | Operational |
| `carrier_id` | Contracted carrier | VARCHAR(30) | Required | None | Valid `carrier_id` | None | FK (`carriers`), Indexed | Source | Operational |
| `lane_id` | Transit lane | VARCHAR(30) | Required | None | Valid `lane_id` | None | FK (`lanes`), Indexed | Source | Operational |
| `service_level`| Requested service tier| VARCHAR(20) | Required | `STANDARD` | `ServiceLevel` | None | NOT NULL | Source | Operational |
| `ship_date` | Date cargo dispatched | DATE | Required | None | Valid date | Date | NOT NULL, Indexed | Source | Operational |
| `delivery_due_date` | SLA delivery target | DATE | Required | None | Valid date >= ship_date | Date | `CHECK(ship <= due)` | Source | Operational |
| `delivered_at` | Actual delivery time | DATETIME | Optional | `NULL` | Valid timestamp | UTC | NULL until delivered | Operational | Operational |
| `actual_length_cm`| Physical length | FLOAT | Required | None | Value > 0 | Centimeters | `CHECK(length > 0)` | Operational | Operational |
| `actual_width_cm` | Physical width | FLOAT | Required | None | Value > 0 | Centimeters | `CHECK(width > 0)` | Operational | Operational |
| `actual_height_cm`| Physical height | FLOAT | Required | None | Value > 0 | Centimeters | `CHECK(height > 0)` | Operational | Operational |
| `actual_weight_kg`| Certified scale weight | FLOAT | Required | None | Value > 0 | Kilograms | `CHECK(weight > 0)` | Operational | Operational |
| `declared_weight_kg`| Shipper declared wt | FLOAT | Required | None | Value > 0 | Kilograms | `CHECK(weight > 0)` | Source | Operational |
| `chargeable_weight_kg`| Billed rating weight| FLOAT | Required | None | $\max(\text{actual}, \frac{L \times W \times H}{5000})$ | Kilograms | `CHECK(weight > 0)` | Derived | Operational |
| `currency` | Billing currency | VARCHAR(3) | Required | `USD` | ISO 4217 code | None | NOT NULL | Source | Operational |
| `shipment_status` | Operational state | VARCHAR(20) | Required | `BOOKED` | `ShipmentStatus` (BOOKED, IN_TRANSIT, DELIVERED, etc.) | None | NOT NULL, Indexed | Operational | Operational |
| `created_at` | Record creation time | DATETIME | Required | `utcnow()` | Valid timestamp | UTC | NOT NULL | System | Historical |

---

### 2.6 `shipment_legs`
*Primary Key*: `shipment_leg_id` (e.g. `LEG-SHP-2026-000001-01`)

| Field Name | Business Meaning | DB Type | Status | Default | Allowed Values / Enum | Units | Constraints | Data Classification | Lifecycle Context |
|---|---|---|---|---|---|---|---|---|---|
| `shipment_leg_id`| Immutable leg ID | VARCHAR(40) | Required | None | `LEG-{shipment}-{seq}` | None | PK, Indexed | Source | Operational |
| `shipment_id` | Parent shipment | VARCHAR(30) | Required | None | Valid `shipment_id` | None | FK (`shipments`), Indexed | Source | Operational |
| `leg_sequence` | Segment sequence | INTEGER | Required | None | Value >= 1 | Sequence | Unique per shipment | Source | Operational |
| `origin_location_code` | Leg origin node | VARCHAR(20) | Required | None | Valid hub code | None | NOT NULL | Source | Operational |
| `destination_location_code`| Leg destination | VARCHAR(20) | Required | None | Valid hub code | None | NOT NULL | Source | Operational |
| `departure_at` | Actual departure | DATETIME | Optional | `NULL` | Valid timestamp | UTC | NULL until dispatched | Operational | Operational |
| `arrival_at` | Actual arrival | DATETIME | Optional | `NULL` | Valid timestamp >= departure | UTC | `CHECK(dep <= arr)` | Operational | Operational |
| `leg_status` | Leg state | VARCHAR(20) | Required | `PENDING` | `ShipmentLegStatus` | None | NOT NULL | Operational | Operational |

---

### 2.7 `weight_measurements`
*Primary Key*: `weight_measurement_id` (e.g. `WM-SHP-2026-000001-01`)

| Field Name | Business Meaning | DB Type | Status | Default | Allowed Values / Enum | Units | Constraints | Data Classification | Lifecycle Context |
|---|---|---|---|---|---|---|---|---|---|
| `weight_measurement_id`| Immutable reading ID| VARCHAR(40) | Required | None | `WM-{shipment}-{seq}` | None | PK, Indexed | Source | Operational |
| `shipment_id` | Parent shipment | VARCHAR(30) | Required | None | Valid `shipment_id` | None | FK (`shipments`), Indexed | Source | Operational |
| `measurement_type` | Certificate type | VARCHAR(30) | Required | `ORIGIN_SCALE` | `MeasurementType` | None | NOT NULL | Source | Operational |
| `length_cm` | Measured length | FLOAT | Optional | `NULL` | Value > 0 | Centimeters | `CHECK(len > 0)` | Source | Operational |
| `width_cm` | Measured width | FLOAT | Optional | `NULL` | Value > 0 | Centimeters | `CHECK(wid > 0)` | Source | Operational |
| `height_cm` | Measured height | FLOAT | Optional | `NULL` | Value > 0 | Centimeters | `CHECK(hgt > 0)` | Source | Operational |
| `weight_kg` | Scale weight | FLOAT | Required | None | Value > 0 | Kilograms | `CHECK(wt > 0)` | Source | Operational |
| `measured_at` | Scale timestamp | DATETIME | Required | `utcnow()` | Valid timestamp | UTC | NOT NULL | Source | Operational |
| `source` | Certifying entity | VARCHAR(30) | Required | `CARRIER` | `MeasurementSource` | None | NOT NULL | Source | Operational |
| `is_accepted` | Audit accepted flag | BOOLEAN | Required | `True` | Boolean | None | NOT NULL | Operational | Operational |

---

### 2.8 `accessorials`
*Primary Key*: `accessorial_id` (e.g. `ACC-000001`)

| Field Name | Business Meaning | DB Type | Status | Default | Allowed Values / Enum | Units | Constraints | Data Classification | Lifecycle Context |
|---|---|---|---|---|---|---|---|---|---|
| `accessorial_id` | Immutable fee ID | VARCHAR(30) | Required | None | `ACC-[0-9]{6}` | None | PK, Indexed | Source | Operational |
| `accessorial_code`| Contractual code | VARCHAR(30) | Required | None | E.g. `LIFTGATE`, `DETENTION` | None | Unique, Indexed | Source | Operational |
| `description` | Service explanation | VARCHAR(200)| Required | None | Valid description | None | NOT NULL | Source | Operational |
| `charge_method` | Calculation logic | VARCHAR(20) | Required | `FLAT` | `ChargeMethod` (FLAT, PER_KG, PER_HOUR, etc.) | None | NOT NULL | Source | Operational |
| `rate_amount` | Contracted unit fee | FLOAT | Required | None | Value >= 0 | Currency ($) | `CHECK(rate >= 0)` | Source | Operational |
| `currency` | Billing currency | VARCHAR(3) | Required | `USD` | ISO 4217 code | None | NOT NULL | Source | Operational |
| `taxable` | Taxable surcharge | BOOLEAN | Required | `False` | Boolean | None | NOT NULL | Source | Operational |
| `requires_evidence`| Mandatory POD proof | BOOLEAN | Required | `True` | Boolean | None | NOT NULL | Source | Operational |
| `status` | Catalog status | VARCHAR(20) | Required | `ACTIVE` | `AccessorialStatus` | None | NOT NULL | Operational | Operational |
| `effective_from` | Tariff start date | DATE | Required | None | Valid date | Date | NOT NULL | Source | Operational |
| `effective_to` | Tariff end date | DATE | Optional | `NULL` | Valid date >= effective_from | Date | NULL = open-ended | Source | Operational |

---

### 2.9 `shipment_accessorials`
*Primary Key*: `shipment_accessorial_id` (e.g. `SA-SHP-2026-000001-01`)

| Field Name | Business Meaning | DB Type | Status | Default | Allowed Values / Enum | Units | Constraints | Data Classification | Lifecycle Context |
|---|---|---|---|---|---|---|---|---|---|
| `shipment_accessorial_id`| Immutable bridge ID| VARCHAR(50) | Required | None | `SA-{shipment}-{seq}` | None | PK, Indexed | Source | Operational |
| `shipment_id` | Linked shipment | VARCHAR(30) | Required | None | Valid `shipment_id` | None | FK (`shipments`), Indexed | Source | Operational |
| `accessorial_id` | Linked accessorial | VARCHAR(30) | Required | None | Valid `accessorial_id` | None | FK (`accessorials`), Indexed | Source | Operational |
| `quantity` | Billed duration/units | FLOAT | Required | 1.0 | Value > 0 (e.g. dwell hrs) | Units/Hours | `CHECK(quantity > 0)`| Operational | Operational |
| `authorized` | Verified by shipper | BOOLEAN | Required | `True` | Boolean | None | NOT NULL | Operational | Operational |
| `evidence_reference`| Linked POD/GPS slip | VARCHAR(100)| Optional | `NULL` | Document reference | None | NULL if unverified | Operational | Operational |
| `created_at` | Record creation time | DATETIME | Required | `utcnow()` | Valid timestamp | UTC | NOT NULL | System | Historical |

---

### 2.10 `delivery_evidence`
*Primary Key*: `delivery_evidence_id` (e.g. `DEV-SHP-2026-000001`)

| Field Name | Business Meaning | DB Type | Status | Default | Allowed Values / Enum | Units | Constraints | Data Classification | Lifecycle Context |
|---|---|---|---|---|---|---|---|---|---|
| `delivery_evidence_id`| Immutable evidence ID| VARCHAR(40)| Required | None | `DEV-{shipment_id}` | None | PK, Indexed | Operational | Operational |
| `shipment_id` | Linked shipment | VARCHAR(30) | Required | None | Valid `shipment_id` | None | FK (`shipments`), Unique | Operational | Operational |
| `delivered_at` | Consignee signature time| DATETIME | Required | None | Valid timestamp | UTC | NOT NULL | Operational | Operational |
| `recipient_name` | Receiving agent name | VARCHAR(100)| Required | None | Valid name | None | NOT NULL | Operational | Operational |
| `signed_pod_ref` | Digital document ref | VARCHAR(100)| Optional | `NULL` | Document ref | None | Indexed | Operational | Operational |
| `facility_dock_type` | Destination dock type | VARCHAR(50) | Required | `STANDARD_DOCK`| `STANDARD_DOCK`, `GROUND_LEVEL`, `RESIDENTIAL` | None | NOT NULL | Operational | Operational |
| `liftgate_actually_used`| Physical liftgate proof | BOOLEAN | Required | `False` | Boolean | None | NOT NULL | Operational | Operational |
| `detention_minutes_recorded`| GPS facility dwell | INTEGER | Required | 0 | Value >= 0 | Minutes | `CHECK(mins >= 0)` | Operational | Operational |
| `created_at` | Record creation time | DATETIME | Required | `utcnow()` | Valid timestamp | UTC | NOT NULL | System | Historical |

---

### 2.11 `freight_invoices`
*Primary Key*: `invoice_id` (e.g. `FINV-2026-000001`)

| Field Name | Business Meaning | DB Type | Status | Default | Allowed Values / Enum | Units | Constraints | Data Classification | Lifecycle Context |
|---|---|---|---|---|---|---|---|---|---|
| `invoice_id` | Immutable invoice ID | VARCHAR(40) | Required | None | `FINV-{year}-{seq}` | None | PK, Indexed | System | Operational |
| `carrier_id` | Invoicing carrier | VARCHAR(30) | Required | None | Valid `carrier_id` | None | FK (`carriers`), Indexed | Source | Operational |
| `shipment_id` | Normalized shipment FK | VARCHAR(30) | Optional | `NULL` | Valid `shipment_id` or NULL if rejected | None | FK (`shipments`), Indexed | Operational | Operational |
| `raw_shipment_reference`| External shipment ID billed| VARCHAR(50)| Required | None | Untrusted raw string from carrier invoice | None | NOT NULL, Indexed | Source | Operational |
| `reference_rejection_reason`| Rejection note for invalid shipment ref | VARCHAR(255)| Optional | `NULL` | Explanation string | None | Set when shipment_id is NULL | Derived | Operational |
| `invoice_number` | Carrier invoice number | VARCHAR(50) | Required | None | Invoice number | None | Unique per carrier | Source | Operational |
| `invoice_date` | Date invoice issued | DATE | Required | None | Valid date | Date | NOT NULL, Indexed | Source | Operational |
| `service_period_start`| Freight billing start | DATE | Required | None | Valid date | Date | NOT NULL | Source | Operational |
| `service_period_end` | Freight billing end | DATE | Required | None | Valid date >= start | Date | `CHECK(start <= end)`| Source | Operational |
| `due_date` | Payment due date | DATE | Required | None | Valid date | Date | NOT NULL | Source | Operational |
| `currency` | Invoice currency | VARCHAR(3) | Required | `USD` | ISO 4217 code | None | NOT NULL | Source | Operational |
| `billed_total` | Total gross billed amount| FLOAT | Required | 0.0 | Value >= 0 | Currency ($) | `CHECK(billed >= 0)` | Source | Operational |
| `expected_total` | Contractual expected total| FLOAT | Required | 0.0 | Calculated by rating engine | Currency ($) | `CHECK(expected >= 0)`| Derived | Operational |
| `variance_amount` | Billed - Expected variance | FLOAT | Required | 0.0 | Net financial delta | Currency ($) | Derived | Derived | Operational |
| `invoice_status` | Operational status | VARCHAR(30) | Required | `SUBMITTED` | `InvoiceStatus` (SUBMITTED, PENDING_AUDIT, VALIDATED_MATCH, etc.) | None | NOT NULL, Indexed | Operational | Operational |
| `validation_status`| Audit result verdict | VARCHAR(30) | Required | `UNAUDITED` | `ValidationStatus` (UNAUDITED, PASSED, FAILED) | None | NOT NULL, Indexed | Operational | Operational |
| `duplicate_group_id`| Duplicate cluster ID | VARCHAR(30) | Optional | `NULL` | Valid `group_id` | None | FK (`duplicate_invoice_groups`)| Derived | Operational |
| `fingerprint_hash`| SHA-256 duplicate key | VARCHAR(64) | Optional | `NULL` | SHA-256 hash `(carrier:raw_ref:amount)` | None | Indexed | Derived | Operational |
| `created_at` | Record creation time | DATETIME | Required | `utcnow()` | Valid timestamp | UTC | NOT NULL | System | Historical |

---

### 2.12 `invoice_lines`
*Primary Key*: `invoice_line_id` (e.g. `FLINE-FINV-2026-000001-01`)

| Field Name | Business Meaning | DB Type | Status | Default | Allowed Values / Enum | Units | Constraints | Data Classification | Lifecycle Context |
|---|---|---|---|---|---|---|---|---|---|
| `invoice_line_id`| Immutable line ID | VARCHAR(50) | Required | None | `FLINE-{invoice}-{seq}` | None | PK, Indexed | System | Operational |
| `invoice_id` | Parent invoice | VARCHAR(40) | Required | None | Valid `invoice_id` | None | FK (`freight_invoices`), Indexed | Source | Operational |
| `line_number` | Line sequence number | INTEGER | Required | None | Value >= 1 | Sequence | Unique per invoice | Source | Operational |
| `line_type` | Classification of charge| VARCHAR(30) | Required | `BASE_LINEHAUL`| `InvoiceLineType` (BASE_LINEHAUL, FUEL_SURCHARGE, ACCESSORIAL, etc.) | None | NOT NULL | Source | Operational |
| `accessorial_id` | Contracted accessorial | VARCHAR(30) | Optional | `NULL` | Valid `accessorial_id` | None | FK (`accessorials`), Indexed | Source | Operational |
| `description` | Charge description | VARCHAR(200)| Required | None | Valid string | None | NOT NULL | Source | Operational |
| `quantity` | Billed units | FLOAT | Required | 1.0 | Value > 0 | Units/Kg/Hrs | NOT NULL | Source | Operational |
| `unit_of_measure`| Unit type | VARCHAR(20) | Required | `KG` | `KG`, `KM`, `HOUR`, `FLAT` | None | NOT NULL | Source | Operational |
| `unit_rate` | Billed unit rate | FLOAT | Required | 0.0 | Value >= 0 | Currency ($) | NOT NULL | Source | Operational |
| `billed_amount` | Billed charge | FLOAT | Required | 0.0 | Value >= 0 | Currency ($) | `CHECK(billed >= 0)` | Source | Operational |
| `expected_amount`| Contractual calculated | FLOAT | Required | 0.0 | Value >= 0 | Currency ($) | `CHECK(expected >= 0)`| Derived | Operational |
| `variance_amount`| Billed - Expected delta | FLOAT | Required | 0.0 | Net line variance | Currency ($) | Derived | Derived | Operational |
| `evidence_reference`| Supporting document | VARCHAR(100)| Optional | `NULL` | POD/ELD document reference | None | NULL if unverified | Operational | Operational |
| `source_reference`| Contractual source doc | VARCHAR(100)| Optional | `NULL` | RateCard / Rule ID | None | Source citation | Operational | Operational |
| `created_at` | Record creation time | DATETIME | Required | `utcnow()` | Valid timestamp | UTC | NOT NULL | System | Historical |

---

### 2.13 `audit_exceptions`
*Primary Key*: `exception_id` (e.g. `FEX-2026-000001`)

| Field Name | Business Meaning | DB Type | Status | Default | Allowed Values / Enum | Units | Constraints | Data Classification | Lifecycle Context |
|---|---|---|---|---|---|---|---|---|---|
| `exception_id` | Immutable ticket ID | VARCHAR(40) | Required | None | `FEX-{year}-{seq}` | None | PK, Indexed | System | Operational |
| `invoice_id` | Flagged invoice | VARCHAR(40) | Required | None | Valid `invoice_id` | None | FK (`freight_invoices`), Indexed | Derived | Operational |
| `invoice_line_id`| Specific flagged line | VARCHAR(50) | Optional | `NULL` | Valid `invoice_line_id` | None | FK (`invoice_lines`), Indexed | Derived | Operational |
| `shipment_id` | Flagged shipment | VARCHAR(30) | Optional | `NULL` | Valid `shipment_id` | None | FK (`shipments`), Indexed | Derived | Operational |
| `exception_type` | Discrepancy category | VARCHAR(40) | Required | None | `ExceptionType` (5 negative scenarios) | None | NOT NULL, Indexed | Derived | Operational |
| `severity` | Business criticality | VARCHAR(20) | Required | `CRITICAL` | `ExceptionSeverity` (LOW, MEDIUM, HIGH, CRITICAL) | None | NOT NULL | Derived | Operational |
| `expected_amount`| Contractual baseline | FLOAT | Required | 0.0 | Calculated amount | Currency ($) | NOT NULL | Derived | Operational |
| `billed_amount` | Erroneous billed charge | FLOAT | Required | 0.0 | Billed amount | Currency ($) | NOT NULL | Source | Operational |
| `disputed_amount`| Financial variance | FLOAT | Required | 0.0 | Disputed overcharge | Currency ($) | NOT NULL | Derived | Operational |
| `currency` | Currency | VARCHAR(3) | Required | `USD` | ISO 4217 code | None | NOT NULL | Operational | Operational |
| `explanation` | Contextual justification| TEXT | Required | None | Detailed audit explanation | None | NOT NULL | Derived | Operational |
| `evidence_json` | JSON proof snapshot | TEXT | Optional | `NULL` | Structured snapshot | None | Snapshot | Derived | Operational |
| `exception_status`| Triage state | VARCHAR(30) | Required | `OPEN` | `ExceptionStatus` (OPEN, UNDER_REVIEW, DISPUTED, AUTO_RESOLVED, etc.) | None | NOT NULL, Indexed | Operational | Operational |
| `detected_at` | Audit detection time | DATETIME | Required | `utcnow()` | Valid timestamp | UTC | NOT NULL | System | Historical |
| `resolved_at` | Settlement timestamp | DATETIME | Optional | `NULL` | Valid timestamp | UTC | Set when resolved | Operational | Historical |

---

### 2.14 `credit_notes`
*Primary Key*: `credit_note_id` (e.g. `CN-2026-000001`)

| Field Name | Business Meaning | DB Type | Status | Default | Allowed Values / Enum | Units | Constraints | Data Classification | Lifecycle Context |
|---|---|---|---|---|---|---|---|---|---|
| `credit_note_id` | Immutable credit ID | VARCHAR(40) | Required | None | `CN-{year}-{seq}` | None | PK, Indexed | System | Operational |
| `exception_id` | Disputed exception | VARCHAR(40) | Optional | `NULL` | Valid `exception_id` | None | FK (`audit_exceptions`), Indexed | Source | Operational |
| `invoice_id` | Target invoice credited | VARCHAR(40) | Required | None | Valid `invoice_id` | None | FK (`freight_invoices`), Indexed | Source | Operational |
| `carrier_id` | Invoicing carrier | VARCHAR(30) | Required | None | Valid `carrier_id` | None | FK (`carriers`), Indexed | Source | Operational |
| `credit_note_number`| Carrier credit doc ref | VARCHAR(50) | Required | None | Credit note document number | None | Unique, Indexed | Source | Operational |
| `issue_date` | Date issued by carrier | DATE | Required | None | Valid date | Date | NOT NULL, Indexed | Source | Operational |
| `currency` | Currency | VARCHAR(3) | Required | `USD` | ISO 4217 code | None | NOT NULL | Source | Operational |
| `credit_amount` | Reimbursed amount | FLOAT | Required | None | Value > 0 | Currency ($) | `CHECK(credit_amount > 0)`| Source | Operational |
| `approval_status`| Finance approval state | VARCHAR(30) | Required | `PENDING_APPROVAL`| `CreditNoteApprovalStatus` | None | NOT NULL | Operational | Operational |
| `reconciliation_status`| Application state | VARCHAR(30) | Required | `UNAPPLIED` | `CreditNoteReconciliationStatus` | None | NOT NULL, Indexed | Operational | Operational |
| `created_at` | Record creation time | DATETIME | Required | `utcnow()` | Valid timestamp | UTC | NOT NULL | System | Historical |

---

### 2.15 `duplicate_invoice_groups`
*Primary Key*: `group_id` (e.g. `DUP-000001`)

| Field Name | Business Meaning | DB Type | Status | Default | Allowed Values / Enum | Units | Constraints | Data Classification | Lifecycle Context |
|---|---|---|---|---|---|---|---|---|---|
| `group_id` | Unique duplicate cluster| VARCHAR(30) | Required | None | `DUP-[0-9]{6}` | None | PK, Indexed | System | Operational |
| `carrier_id` | Carrier reference | VARCHAR(30) | Required | None | Valid `carrier_id` | None | FK (`carriers`), Indexed | Source | Operational |
| `fingerprint_hash`| SHA-256 duplicate key | VARCHAR(64) | Required | None | Hexadecimal 64-char hash | None | Unique, Indexed | Derived | Operational |
| `canonical_invoice_id`| Original invoice ID | VARCHAR(40) | Optional | `NULL` | First valid invoice ID | None | Indexed | Derived | Operational |
| `invoice_count` | Duplicate cluster size | INTEGER | Required | 1 | Value >= 1 | Count | NOT NULL | Derived | Operational |
| `created_at` | Cluster creation time | DATETIME | Required | `utcnow()` | Valid timestamp | UTC | NOT NULL | System | Historical |

---

### 2.16 `invoice_validation_runs`
*Primary Key*: `validation_run_id` (e.g. `VRUN-2026-000001`)

| Field Name | Business Meaning | DB Type | Status | Default | Allowed Values / Enum | Units | Constraints | Data Classification | Lifecycle Context |
|---|---|---|---|---|---|---|---|---|---|
| `validation_run_id`| Audit execution ID | VARCHAR(40) | Required | None | `VRUN-{year}-{seq}` | None | PK, Indexed | System | Operational |
| `invoice_id` | Target invoice audited | VARCHAR(40) | Required | None | Valid `invoice_id` | None | FK (`freight_invoices`), Indexed | Operational | Operational |
| `run_at` | Timestamp of audit run | DATETIME | Required | `utcnow()` | Valid timestamp | UTC | NOT NULL | System | Historical |
| `actor` | Executor identity | VARCHAR(50) | Required | `SYSTEM_AUDITOR`| E.g. `SYSTEM_AUDITOR`, `OPERATOR` | None | NOT NULL | Operational | Historical |
| `rules_applied_count`| Number of rules tested| INTEGER | Required | 0 | Count >= 0 | Count | NOT NULL | Operational | Historical |
| `exceptions_detected_count`| Discrepancies raised | INTEGER | Required | 0 | Count >= 0 | Count | NOT NULL | Operational | Historical |
| `summary_verdict`| Audit outcome | VARCHAR(30) | Required | None | `PASSED`, `FAILED` | None | NOT NULL | Operational | Historical |
| `details_json` | Detailed rule breakdown| TEXT | Optional | `NULL` | JSON structure | None | Snapshot | Operational | Historical |

---

### 2.17 `audit_events`
*Primary Key*: `event_id` (e.g. `AUD-2026-000001`)

| Field Name | Business Meaning | DB Type | Status | Default | Allowed Values / Enum | Units | Constraints | Data Classification | Lifecycle Context |
|---|---|---|---|---|---|---|---|---|---|
| `event_id` | Immutable event ID | VARCHAR(40) | Required | None | `AUD-{year}-{seq}` | None | PK, Indexed | System | Historical |
| `entity_type` | Affected entity table | VARCHAR(50) | Required | None | E.g. `FREIGHT_INVOICE`, `CARRIER` | None | NOT NULL, Indexed | System | Historical |
| `entity_id` | Affected entity PK | VARCHAR(50) | Required | None | Target entity string ID | None | NOT NULL, Indexed | System | Historical |
| `event_type` | Action category | VARCHAR(50) | Required | None | `CREATED`, `VALIDATED`, `DISPUTED` | None | NOT NULL, Indexed | System | Historical |
| `actor` | Initiating user / system| VARCHAR(50) | Required | `SYSTEM_AUDITOR`| User ID or service agent | None | NOT NULL | System | Historical |
| `payload_json` | Snapshot of mutation | TEXT | Optional | `NULL` | JSON state diff | None | Snapshot | System | Historical |
| `notes` | Human-readable note | VARCHAR(255)| Optional | `NULL` | Context summary | None | Optional | System | Historical |
| `timestamp` | Time event occurred | DATETIME | Required | `utcnow()` | Valid timestamp | UTC | NOT NULL, Indexed | System | Historical |

---

### 2.18 `entity_status_history`
*Primary Key*: `history_id` (e.g. `HIST-2026-000001`)

| Field Name | Business Meaning | DB Type | Status | Default | Allowed Values / Enum | Units | Constraints | Data Classification | Lifecycle Context |
|---|---|---|---|---|---|---|---|---|---|
| `history_id` | Immutable history ID | VARCHAR(40) | Required | None | `HIST-{year}-{seq}` | None | PK, Indexed | System | Historical |
| `entity_name` | Name of entity class | VARCHAR(50) | Required | None | `Shipment`, `FreightInvoice`, etc. | None | NOT NULL, Indexed | System | Historical |
| `entity_id` | Entity primary key | VARCHAR(50) | Required | None | Target entity ID | None | NOT NULL, Indexed | System | Historical |
| `from_status` | Status before change | VARCHAR(50) | Required | None | Valid status enum value | None | NOT NULL | Operational | Historical |
| `to_status` | New transitioned status| VARCHAR(50) | Required | None | Valid status enum value | None | NOT NULL | Operational | Historical |
| `transition_reason`| Justification of change| VARCHAR(255)| Optional | `NULL` | Explanation string | None | Optional | Operational | Historical |
| `changed_by` | Actor who changed state| VARCHAR(50) | Required | `SYSTEM_AUDITOR`| User or system | None | NOT NULL | System | Historical |
| `changed_at` | Timestamp of transition| DATETIME | Required | `utcnow()` | Valid timestamp | UTC | NOT NULL, Indexed | System | Historical |
