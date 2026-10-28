# Relational Schema & System Architecture (Phase 1)

## 1. Complete Entity Relationship Diagram (ERD)

```mermaid
erDiagram
    Carrier ||--o{ RateCard : "issues (1:N)"
    Carrier ||--o{ Shipment : "transports (1:N)"
    Carrier ||--o{ FreightInvoice : "bills (1:N)"
    Carrier ||--o{ CreditNote : "grants (1:N)"
    Carrier ||--o{ DuplicateInvoiceGroup : "owns (1:N)"

    Lane ||--o{ RateCard : "governs (1:N)"
    Lane ||--o{ Shipment : "routes (1:N)"

    RateCard ||--|{ RateTier : "contains tiers (1:N)"

    Shipment ||--|{ ShipmentLeg : "comprises legs (1:N)"
    Shipment ||--|{ WeightMeasurement : "measured by (1:N)"
    Shipment ||--o| DeliveryEvidence : "verified by (1:1)"
    Shipment ||--o{ ShipmentAccessorial : "has accessorials (1:N)"
    Accessorial ||--o{ ShipmentAccessorial : "assigned to (1:N)"

    Shipment ||--o{ FreightInvoice : "billed by (1:N)"
    FreightInvoice ||--|{ InvoiceLine : "itemizes (1:N)"
    Accessorial ||--o{ InvoiceLine : "referenced by (0..1:N)"

    DuplicateInvoiceGroup ||--o{ FreightInvoice : "clusters (1:N)"
    FreightInvoice ||--o{ InvoiceValidationRun : "audited in (1:N)"

    FreightInvoice ||--o{ AuditException : "raises (1:N)"
    InvoiceLine ||--o{ AuditException : "flags (0..1:N)"
    Shipment ||--o{ AuditException : "targets (0..1:N)"

    AuditException ||--o{ CreditNote : "settled by (1:N partial credits)"
    FreightInvoice ||--o{ CreditNote : "credited to (1:N)"

    Carrier {
        string carrier_id PK "CAR-000001"
        string carrier_code UK
        string carrier_name
        string status
        string country_code
    }

    Lane {
        string lane_id PK "LANE-000001"
        string origin_location_code
        string destination_location_code
        string origin_city
        string destination_city
        float distance_km
        string status
    }

    RateCard {
        string rate_card_id PK "RATE-CAR-000001-2026-01"
        string carrier_id FK
        string lane_id FK
        string service_level
        string currency
        date effective_from
        date effective_to
        float base_rate
        float minimum_charge
        float dimensional_weight_divisor
        string status
    }

    RateTier {
        string rate_tier_id PK "TIER-RATE-CAR-000001-2026-01-01"
        string rate_card_id FK
        int tier_sequence
        float min_weight_kg
        float max_weight_kg
        float rate_per_kg
        float flat_surcharge
    }

    Accessorial {
        string accessorial_id PK "ACC-000001"
        string accessorial_code UK
        string description
        string charge_method
        float rate_amount
        string currency
        boolean requires_evidence
        string status
        date effective_from
        date effective_to
    }

    Shipment {
        string shipment_id PK "SHP-2026-000001"
        string carrier_id FK
        string lane_id FK
        string service_level
        date ship_date
        date delivery_due_date
        datetime delivered_at
        float actual_weight_kg
        float chargeable_weight_kg
        string shipment_status
    }

    ShipmentLeg {
        string shipment_leg_id PK "LEG-SHP-2026-000001-01"
        string shipment_id FK
        int leg_sequence
        string origin_location_code
        string destination_location_code
        string leg_status
    }

    WeightMeasurement {
        string weight_measurement_id PK "WM-SHP-2026-000001-01"
        string shipment_id FK
        string measurement_type
        float weight_kg
        string source
        boolean is_accepted
    }

    DeliveryEvidence {
        string delivery_evidence_id PK "DEV-SHP-2026-000001"
        string shipment_id FK,UK
        datetime delivered_at
        string recipient_name
        string signed_pod_ref
        string facility_dock_type
        boolean liftgate_actually_used
        int detention_minutes_recorded
    }

    ShipmentAccessorial {
        string shipment_accessorial_id PK "SA-SHP-2026-000001-01"
        string shipment_id FK
        string accessorial_id FK
        float quantity
        boolean authorized
        string evidence_reference
    }

    FreightInvoice {
        string invoice_id PK "FINV-2026-000001"
        string carrier_id FK
        string shipment_id FK "Nullable if raw reference is rejected"
        string raw_shipment_reference "Untrusted carrier input"
        string reference_rejection_reason
        string invoice_number
        date invoice_date
        float billed_total
        float expected_total
        float variance_amount
        string invoice_status
        string validation_status
        string duplicate_group_id FK
        string fingerprint_hash
    }

    InvoiceLine {
        string invoice_line_id PK "FLINE-FINV-2026-000001-01"
        string invoice_id FK
        int line_number
        string line_type
        string accessorial_id FK
        float quantity
        float unit_rate
        float billed_amount
        float expected_amount
        float variance_amount
    }

    AuditException {
        string exception_id PK "FEX-2026-000001"
        string invoice_id FK
        string invoice_line_id FK
        string shipment_id FK
        string exception_type
        string severity
        float expected_amount
        float billed_amount
        float disputed_amount
        string exception_status
    }

    CreditNote {
        string credit_note_id PK "CN-2026-000001"
        string exception_id FK
        string invoice_id FK
        string carrier_id FK
        string credit_note_number UK
        float credit_amount
        string approval_status
        string reconciliation_status
    }
```

---

## 2. Cardinalities and Relationships

1. **Carrier (1 : N) RateCard**: A carrier maintains one or multiple active tariffs across different lanes, service levels, and contractual validity dates.
2. **Lane (1 : N) RateCard**: Multiple carriers can publish rate cards on the same lane.
3. **RateCard (1 : N) RateTier**: Weight-break pricing intervals ($0 - 500\text{ kg}$, $500 - 2000\text{ kg}$) are modeled explicitly in `RateTier` with `tier_sequence`.
4. **Carrier (1 : N) Shipment**: A carrier executes multiple shipments.
5. **Lane (1 : N) Shipment**: Shipments travel over a specified geographic lane.
6. **Shipment (1 : N) ShipmentLeg**: Complex freight movements contain 1 or more sequential legs with timestamps.
7. **Shipment (1 : N) WeightMeasurement**: Origin scale, destination re-weigh, and dimensional scans are captured as certified readings.
8. **Shipment (N : M) Accessorial**: Linked via `ShipmentAccessorial` bridge table with authorized status, duration/quantity, and document evidence.
9. **Shipment (1 : 1) DeliveryEvidence**: Official POD receipt capturing signed receiver name, dock type, liftgate deployment, and GPS dwell time.
10. **Carrier (1 : N) FreightInvoice**: Carriers submit multiple periodic invoices.
11. **Shipment (1 : N) FreightInvoice**: Supports legitimate partial invoices (e.g. linehaul billed first, supplemental accessorial billed later) and repeat/duplicate invoices.
12. **FreightInvoice (1 : N) InvoiceLine**: Line charges (Linehaul, Fuel, Accessorial, Tax, Misc).
13. **FreightInvoice (1 : N) AuditException**: Discrepancies raised at invoice header or line levels.
14. **InvoiceLine (1 : N) AuditException**: Multiple independent defects on a single line are supported.
15. **AuditException (1 : N) CreditNote**: Partial credit notes settle a disputed exception incrementally.
16. **FreightInvoice (1 : N) AuditEvent**: Immutable write-only log recording every audit, approval, dispute, and override.
17. **Entity (1 : N) EntityStatusHistory**: Explicit historical log recording every state transition.

---

## 3. Untrusted External Shipment Reference Staging

In negative testing and real-world billing, carriers frequently submit invalid, typo-ridden, or fictitious shipment references. To support this without violating SQL foreign key constraints:
- `raw_shipment_reference` (VARCHAR) stores the unvalidated string submitted on the carrier invoice.
- `shipment_id` (VARCHAR) is a nullable foreign key.
- When an invoice arrives:
  - If `raw_shipment_reference` matches a valid `Shipment`, `shipment_id` is linked.
  - If `raw_shipment_reference` does not exist in master records, `shipment_id` is set to `NULL`, `reference_rejection_reason` records the rejection reason, and an `AuditException` of type `UNMATCHED_SHIPMENT` is raised.
  - No database foreign key violation occurs, and the bad invoice is isolated and audited cleanly.

---

## 4. Contractual Effective Date Logic

A `RateCard` is contractually applicable for rating a shipment if and only if:

$$\text{effective\_from} \le \text{shipment.ship\_date} \le \text{effective\_to}$$

- `effective_to` is treated as **inclusive**.
- If `effective_to` is `NULL`, the contract is open-ended and currently in force indefinitely.
- The rating engine validates exact match on `(carrier_id, lane_id, service_level)`. If no active rate card satisfies the date interval, the engine refuses to choose an expired tariff and flags an exception.

---

## 5. Lifecycle State Machines

### 5.1 Shipment Lifecycle
```mermaid
stateDiagram-v2
    [*] --> BOOKED
    BOOKED --> IN_TRANSIT
    BOOKED --> CANCELLED
    IN_TRANSIT --> OUT_FOR_DELIVERY
    IN_TRANSIT --> EXCEPTION
    IN_TRANSIT --> CANCELLED
    OUT_FOR_DELIVERY --> DELIVERED
    OUT_FOR_DELIVERY --> EXCEPTION
    EXCEPTION --> IN_TRANSIT
    EXCEPTION --> OUT_FOR_DELIVERY
    EXCEPTION --> DELIVERED
    EXCEPTION --> CANCELLED
    DELIVERED --> [*]
    CANCELLED --> [*]
```

### 5.2 Freight Invoice Lifecycle
```mermaid
stateDiagram-v2
    [*] --> SUBMITTED
    SUBMITTED --> PENDING_AUDIT
    SUBMITTED --> CANCELLED
    PENDING_AUDIT --> VALIDATED_MATCH : Within Tolerance
    PENDING_AUDIT --> EXCEPTION_DISPUTED : Discrepancy Found
    PENDING_AUDIT --> REJECTED : Duplicate / Unmatched
    VALIDATED_MATCH --> PAID
    EXCEPTION_DISPUTED --> EXCEPTION_APPROVED : Override / Credit Note Applied
    EXCEPTION_DISPUTED --> REJECTED : Disputed Unresolved
    EXCEPTION_APPROVED --> PAID
    PAID --> [*]
    REJECTED --> [*]
    CANCELLED --> [*]
```

### 5.3 Audit Exception Lifecycle
```mermaid
stateDiagram-v2
    [*] --> OPEN
    OPEN --> UNDER_REVIEW
    OPEN --> DISPUTED
    OPEN --> APPROVED_OVERRIDE
    OPEN --> AUTO_RESOLVED
    OPEN --> REJECTED
    UNDER_REVIEW --> DISPUTED
    UNDER_REVIEW --> APPROVED_OVERRIDE
    UNDER_REVIEW --> AUTO_RESOLVED
    DISPUTED --> AUTO_RESOLVED : Reconciled with Credit Note
    DISPUTED --> APPROVED_OVERRIDE : Commercial Agreement
    APPROVED_OVERRIDE --> [*]
    AUTO_RESOLVED --> [*]
    REJECTED --> [*]
```

### 5.4 Credit Note Lifecycle
```mermaid
stateDiagram-v2
    [*] --> UNAPPLIED
    UNAPPLIED --> PARTIALLY_APPLIED : Applied Partial Credit
    UNAPPLIED --> FULLY_APPLIED : Full Dispute Cleared
    UNAPPLIED --> REJECTED : Excessive / Invalid
    PARTIALLY_APPLIED --> FULLY_APPLIED : Remainder Settled
    PARTIALLY_APPLIED --> REJECTED
    FULLY_APPLIED --> [*]
    REJECTED --> [*]
```
