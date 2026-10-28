"""
Deterministic Identifier Generator for Freight Invoice Validation System.
Provides immutable, zero-padded, prefixed IDs.
"""

def generate_carrier_id(counter: int) -> str:
    return f"CAR-{counter:06d}"

def generate_rate_card_id(carrier_id: str, year: int = 2026, version_or_seq: int = 1) -> str:
    # Pattern: RATE-CAR-000001-2026-01
    return f"RATE-{carrier_id}-{year}-{version_or_seq:02d}"

def generate_lane_id(counter: int) -> str:
    return f"LANE-{counter:06d}"

def generate_rate_tier_id(rate_card_id: str, tier_seq: int) -> str:
    return f"TIER-{rate_card_id}-{tier_seq:02d}"

def generate_shipment_id(counter: int, year: int = 2026) -> str:
    return f"SHP-{year}-{counter:06d}"

def generate_shipment_leg_id(shipment_id: str, leg_seq: int) -> str:
    return f"LEG-{shipment_id}-{leg_seq:02d}"

def generate_weight_measurement_id(shipment_id: str, measurement_seq: int) -> str:
    return f"WM-{shipment_id}-{measurement_seq:02d}"

def generate_accessorial_id(counter: int) -> str:
    return f"ACC-{counter:06d}"

def generate_shipment_accessorial_id(shipment_id: str, seq: int) -> str:
    return f"SA-{shipment_id}-{seq:02d}"

def generate_delivery_evidence_id(shipment_id: str) -> str:
    return f"DEV-{shipment_id}"

def generate_invoice_id(counter: int, year: int = 2026) -> str:
    return f"FINV-{year}-{counter:06d}"

def generate_invoice_line_id(invoice_id: str, line_number: int) -> str:
    return f"FLINE-{invoice_id}-{line_number:02d}"

def generate_exception_id(counter: int, year: int = 2026) -> str:
    return f"FEX-{year}-{counter:06d}"

def generate_credit_note_id(counter: int, year: int = 2026) -> str:
    return f"CN-{year}-{counter:06d}"

def generate_duplicate_group_id(counter: int) -> str:
    return f"DUP-{counter:06d}"

def generate_validation_run_id(counter: int, year: int = 2026) -> str:
    return f"VRUN-{year}-{counter:06d}"

def generate_audit_event_id(counter: int, year: int = 2026) -> str:
    return f"AUD-{year}-{counter:06d}"

def generate_status_history_id(counter: int, year: int = 2026) -> str:
    return f"HIST-{year}-{counter:06d}"

def generate_ground_truth_label_id(counter: int, year: int = 2026) -> str:
    return f"GTL-{year}-{counter:06d}"

def generate_anomaly_id(counter: int, year: int = 2026) -> str:
    return f"ANOM-{year}-{counter:06d}"
