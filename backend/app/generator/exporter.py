"""
Multi-Format Data Exporter for Freight Invoice Validation System.
Exports all relational entities to CSV, JSON, and SQL formats,
and produces manifest.json and checksums.sha256 manifests.
"""

import csv
import json
import hashlib
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime, date
from sqlalchemy.orm import Session

from backend.app.models.carrier import Carrier
from backend.app.models.lane import Lane
from backend.app.models.accessorial import Accessorial, ShipmentAccessorial
from backend.app.models.rate_card import RateCard, RateTier
from backend.app.models.shipment import Shipment, ShipmentLeg, WeightMeasurement, DeliveryEvidence
from backend.app.models.invoice import FreightInvoice, InvoiceLine, DuplicateInvoiceGroup, InvoiceValidationRun
from backend.app.models.audit_exception import AuditException
from backend.app.models.credit_note import CreditNote
from backend.app.models.audit import AuditEvent, EntityStatusHistory
from backend.app.models.ground_truth import GroundTruthLabel


def json_serializer(obj: Any) -> Any:
    """Helper serializer for dates, datetimes, and enum members."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if hasattr(obj, "value"):
        return obj.value
    raise TypeError(f"Type {type(obj)} not serializable")


class DataExporter:
    """
    Exports synthetic and operational datasets into CSV, JSON, and SQL formats,
    producing SHA-256 integrity checksum manifests.
    """

    def __init__(self, output_dir: str = "data/exports"):
        self.output_dir = Path(output_dir)
        self.csv_dir = self.output_dir / "csv"
        self.json_dir = self.output_dir / "json"
        self.sql_dir = self.output_dir / "sql"

        self.csv_dir.mkdir(parents=True, exist_ok=True)
        self.json_dir.mkdir(parents=True, exist_ok=True)
        self.sql_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def calculate_file_sha256(filepath: Path) -> str:
        hasher = hashlib.sha256()
        with open(filepath, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    def export_all(self, db: Session, seed: int = 20261022) -> Dict[str, Any]:
        """
        Executes complete export pipeline across CSV, JSON, SQL, manifest.json, and checksums.sha256.
        """
        table_data = self._gather_table_data(db)
        checksums = {}
        manifest_entries = {}

        # 1. Export CSVs
        for table_name, data in table_data.items():
            csv_path = self.csv_dir / f"{table_name}.csv"
            self._write_csv(csv_path, data["columns"], data["rows"])
            h = self.calculate_file_sha256(csv_path)
            checksums[f"csv/{csv_path.name}"] = h
            manifest_entries[f"csv/{csv_path.name}"] = {
                "entity": table_name,
                "format": "csv",
                "row_count": len(data["rows"]),
                "columns": data["columns"],
                "sha256": h
            }

        # 2. Export JSONs
        for table_name, data in table_data.items():
            json_path = self.json_dir / f"{table_name}.json"
            self._write_json(json_path, data["columns"], data["rows"])
            h = self.calculate_file_sha256(json_path)
            checksums[f"json/{json_path.name}"] = h
            manifest_entries[f"json/{json_path.name}"] = {
                "entity": table_name,
                "format": "json",
                "row_count": len(data["rows"]),
                "sha256": h
            }

        # 3. Export SQL Seed Script
        sql_path = self.sql_dir / "seed_data.sql"
        self._write_sql(sql_path, table_data)
        sql_hash = self.calculate_file_sha256(sql_path)
        checksums[f"sql/{sql_path.name}"] = sql_hash
        manifest_entries[f"sql/{sql_path.name}"] = {
            "entity": "ALL",
            "format": "sql",
            "sha256": sql_hash
        }

        # 4. Write manifest.json
        manifest_path = self.output_dir / "manifest.json"
        manifest_doc = {
            "dataset_version": "1.0.0",
            "generator_version": "1.0.0",
            "schema_version": "1.0.0",
            "seed": seed,
            "generation_method": "deterministic_pseudo_random_dependency_pipeline",
            "external_source_provenance": {
                "logistics_hubs": "Public domain IATA/DOT US major metropolitan freight hubs (ORD, DFW, ATL, JFK, LAX, etc.)",
                "license": "Public domain / synthetic logistics taxonomy",
                "attribution": "Synthetically generated freight contracts, measurements, and billing ledgers"
            },
            "exported_at": "2026-01-01T08:00:00Z", # Deterministic epoch for reproducible hash
            "total_files": len(checksums),
            "entities": manifest_entries
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest_doc, f, indent=2, sort_keys=True)

        # 5. Write checksums.sha256
        checksum_path = self.output_dir / "checksums.sha256"
        with open(checksum_path, "w", encoding="utf-8") as f:
            for rel_path, h in sorted(checksums.items()):
                f.write(f"{h}  {rel_path}\n")

        return {
            "output_directory": str(self.output_dir),
            "manifest_file": str(manifest_path),
            "checksums_file": str(checksum_path),
            "file_checksums": checksums
        }

    def _gather_table_data(self, db: Session) -> Dict[str, Dict[str, Any]]:
        """Gathers ordered rows and columns for every entity."""
        tables = {}

        # 1. Carriers
        carriers = db.query(Carrier).order_by(Carrier.carrier_id).all()
        tables["carriers"] = {
            "columns": ["carrier_id", "carrier_name", "carrier_code", "status", "country_code", "created_at", "updated_at"],
            "rows": [
                [c.carrier_id, c.carrier_name, c.carrier_code, c.status.value, c.country_code, c.created_at.isoformat(), c.updated_at.isoformat()]
                for c in carriers
            ]
        }

        # 2. Lanes
        lanes = db.query(Lane).order_by(Lane.lane_id).all()
        tables["lanes"] = {
            "columns": ["lane_id", "origin_location_code", "destination_location_code", "origin_city", "destination_city", "origin_country", "destination_country", "distance_km", "status"],
            "rows": [
                [l.lane_id, l.origin_location_code, l.destination_location_code, l.origin_city, l.destination_city, l.origin_country, l.destination_country, l.distance_km, l.status.value]
                for l in lanes
            ]
        }

        # 3. Accessorials
        accessorials = db.query(Accessorial).order_by(Accessorial.accessorial_id).all()
        tables["accessorials"] = {
            "columns": ["accessorial_id", "accessorial_code", "description", "charge_method", "rate_amount", "currency", "taxable", "requires_evidence", "status", "effective_from", "effective_to"],
            "rows": [
                [a.accessorial_id, a.accessorial_code, a.description, a.charge_method.value, a.rate_amount, a.currency, a.taxable, a.requires_evidence, a.status.value, a.effective_from.isoformat(), a.effective_to.isoformat() if a.effective_to else None]
                for a in accessorials
            ]
        }

        # 4. Rate Cards
        rate_cards = db.query(RateCard).order_by(RateCard.rate_card_id).all()
        tables["rate_cards"] = {
            "columns": ["rate_card_id", "carrier_id", "lane_id", "service_level", "currency", "effective_from", "effective_to", "base_rate", "minimum_charge", "dimensional_weight_divisor", "status", "created_at"],
            "rows": [
                [rc.rate_card_id, rc.carrier_id, rc.lane_id, rc.service_level.value, rc.currency, rc.effective_from.isoformat(), rc.effective_to.isoformat() if rc.effective_to else None, rc.base_rate, rc.minimum_charge, rc.dimensional_weight_divisor, rc.status.value, rc.created_at.isoformat()]
                for rc in rate_cards
            ]
        }

        # 5. Rate Tiers
        rate_tiers = db.query(RateTier).order_by(RateTier.rate_tier_id).all()
        tables["rate_tiers"] = {
            "columns": ["rate_tier_id", "rate_card_id", "tier_sequence", "min_weight_kg", "max_weight_kg", "rate_per_kg", "flat_surcharge", "created_at"],
            "rows": [
                [rt.rate_tier_id, rt.rate_card_id, rt.tier_sequence, rt.min_weight_kg, rt.max_weight_kg, rt.rate_per_kg, rt.flat_surcharge, rt.created_at.isoformat()]
                for rt in rate_tiers
            ]
        }

        # 6. Shipments
        shipments = db.query(Shipment).order_by(Shipment.shipment_id).all()
        tables["shipments"] = {
            "columns": ["shipment_id", "carrier_id", "lane_id", "service_level", "ship_date", "delivery_due_date", "delivered_at", "actual_length_cm", "actual_width_cm", "actual_height_cm", "actual_weight_kg", "declared_weight_kg", "chargeable_weight_kg", "currency", "shipment_status", "created_at"],
            "rows": [
                [s.shipment_id, s.carrier_id, s.lane_id, s.service_level.value, s.ship_date.isoformat(), s.delivery_due_date.isoformat(), s.delivered_at.isoformat() if s.delivered_at else None, s.actual_length_cm, s.actual_width_cm, s.actual_height_cm, s.actual_weight_kg, s.declared_weight_kg, s.chargeable_weight_kg, s.currency, s.shipment_status.value, s.created_at.isoformat()]
                for s in shipments
            ]
        }

        # 7. Shipment Legs
        legs = db.query(ShipmentLeg).order_by(ShipmentLeg.shipment_leg_id).all()
        tables["shipment_legs"] = {
            "columns": ["shipment_leg_id", "shipment_id", "leg_sequence", "origin_location_code", "destination_location_code", "departure_at", "arrival_at", "leg_status"],
            "rows": [
                [leg.shipment_leg_id, leg.shipment_id, leg.leg_sequence, leg.origin_location_code, leg.destination_location_code, leg.departure_at.isoformat() if leg.departure_at else None, leg.arrival_at.isoformat() if leg.arrival_at else None, leg.leg_status.value]
                for leg in legs
            ]
        }

        # 8. Weight Measurements
        weights = db.query(WeightMeasurement).order_by(WeightMeasurement.weight_measurement_id).all()
        tables["weight_measurements"] = {
            "columns": ["weight_measurement_id", "shipment_id", "measurement_type", "length_cm", "width_cm", "height_cm", "weight_kg", "measured_at", "source", "is_accepted"],
            "rows": [
                [w.weight_measurement_id, w.shipment_id, w.measurement_type.value, w.length_cm, w.width_cm, w.height_cm, w.weight_kg, w.measured_at.isoformat(), w.source.value, w.is_accepted]
                for w in weights
            ]
        }

        # 9. Shipment Accessorials
        shipment_accs = db.query(ShipmentAccessorial).order_by(ShipmentAccessorial.shipment_accessorial_id).all()
        tables["shipment_accessorials"] = {
            "columns": ["shipment_accessorial_id", "shipment_id", "accessorial_id", "quantity", "authorized", "evidence_reference", "created_at"],
            "rows": [
                [sa.shipment_accessorial_id, sa.shipment_id, sa.accessorial_id, sa.quantity, sa.authorized, sa.evidence_reference, sa.created_at.isoformat()]
                for sa in shipment_accs
            ]
        }

        # 10. Delivery Evidence
        evidences = db.query(DeliveryEvidence).order_by(DeliveryEvidence.delivery_evidence_id).all()
        tables["delivery_evidence"] = {
            "columns": ["delivery_evidence_id", "shipment_id", "delivered_at", "recipient_name", "signed_pod_ref", "facility_dock_type", "liftgate_actually_used", "detention_minutes_recorded", "created_at"],
            "rows": [
                [de.delivery_evidence_id, de.shipment_id, de.delivered_at.isoformat(), de.recipient_name, de.signed_pod_ref, de.facility_dock_type, de.liftgate_actually_used, de.detention_minutes_recorded, de.created_at.isoformat()]
                for de in evidences
            ]
        }

        # 11. Duplicate Groups
        dup_groups = db.query(DuplicateInvoiceGroup).order_by(DuplicateInvoiceGroup.group_id).all()
        tables["duplicate_invoice_groups"] = {
            "columns": ["group_id", "carrier_id", "fingerprint_hash", "canonical_invoice_id", "invoice_count", "created_at"],
            "rows": [
                [dg.group_id, dg.carrier_id, dg.fingerprint_hash, dg.canonical_invoice_id, dg.invoice_count, dg.created_at.isoformat()]
                for dg in dup_groups
            ]
        }

        # 12. Freight Invoices
        invoices = db.query(FreightInvoice).order_by(FreightInvoice.invoice_id).all()
        tables["freight_invoices"] = {
            "columns": ["invoice_id", "carrier_id", "shipment_id", "raw_shipment_reference", "reference_rejection_reason", "invoice_number", "invoice_date", "service_period_start", "service_period_end", "due_date", "currency", "billed_total", "expected_total", "variance_amount", "invoice_status", "validation_status", "duplicate_group_id", "fingerprint_hash", "created_at"],
            "rows": [
                [inv.invoice_id, inv.carrier_id, inv.shipment_id, inv.raw_shipment_reference, inv.reference_rejection_reason, inv.invoice_number, inv.invoice_date.isoformat(), inv.service_period_start.isoformat(), inv.service_period_end.isoformat(), inv.due_date.isoformat(), inv.currency, inv.billed_total, inv.expected_total, inv.variance_amount, inv.invoice_status.value, inv.validation_status.value, inv.duplicate_group_id, inv.fingerprint_hash, inv.created_at.isoformat()]
                for inv in invoices
            ]
        }

        # 13. Invoice Lines
        lines = db.query(InvoiceLine).order_by(InvoiceLine.invoice_line_id).all()
        tables["invoice_lines"] = {
            "columns": ["invoice_line_id", "invoice_id", "line_number", "line_type", "accessorial_id", "description", "quantity", "unit_of_measure", "unit_rate", "billed_amount", "expected_amount", "variance_amount", "evidence_reference", "source_reference", "created_at"],
            "rows": [
                [l.invoice_line_id, l.invoice_id, l.line_number, l.line_type.value, l.accessorial_id, l.description, l.quantity, l.unit_of_measure, l.unit_rate, l.billed_amount, l.expected_amount, l.variance_amount, l.evidence_reference, l.source_reference, l.created_at.isoformat()]
                for l in lines
            ]
        }

        # 14. Invoice Validation Runs
        val_runs = db.query(InvoiceValidationRun).order_by(InvoiceValidationRun.validation_run_id).all()
        tables["invoice_validation_runs"] = {
            "columns": ["validation_run_id", "invoice_id", "run_at", "actor", "rules_applied_count", "exceptions_detected_count", "summary_verdict", "details_json"],
            "rows": [
                [vr.validation_run_id, vr.invoice_id, vr.run_at.isoformat(), vr.actor, vr.rules_applied_count, vr.exceptions_detected_count, vr.summary_verdict, vr.details_json]
                for vr in val_runs
            ]
        }

        # 15. Audit Exceptions
        exceptions = db.query(AuditException).order_by(AuditException.exception_id).all()
        tables["audit_exceptions"] = {
            "columns": ["exception_id", "invoice_id", "invoice_line_id", "shipment_id", "exception_type", "severity", "expected_amount", "billed_amount", "disputed_amount", "currency", "explanation", "evidence_json", "exception_status", "detected_at", "resolved_at"],
            "rows": [
                [ex.exception_id, ex.invoice_id, ex.invoice_line_id, ex.shipment_id, ex.exception_type.value, ex.severity.value, ex.expected_amount, ex.billed_amount, ex.disputed_amount, ex.currency, ex.explanation, ex.evidence_json, ex.exception_status.value, ex.detected_at.isoformat(), ex.resolved_at.isoformat() if ex.resolved_at else None]
                for ex in exceptions
            ]
        }

        # 16. Credit Notes
        credit_notes = db.query(CreditNote).order_by(CreditNote.credit_note_id).all()
        tables["credit_notes"] = {
            "columns": ["credit_note_id", "exception_id", "invoice_id", "carrier_id", "credit_note_number", "issue_date", "currency", "credit_amount", "approval_status", "reconciliation_status", "created_at"],
            "rows": [
                [cn.credit_note_id, cn.exception_id, cn.invoice_id, cn.carrier_id, cn.credit_note_number, cn.issue_date.isoformat(), cn.currency, cn.credit_amount, cn.approval_status.value, cn.reconciliation_status.value, cn.created_at.isoformat()]
                for cn in credit_notes
            ]
        }

        # 17. Ground Truth Labels
        gtls = db.query(GroundTruthLabel).order_by(GroundTruthLabel.label_id).all()
        tables["ground_truth_labels"] = {
            "columns": ["label_id", "anomaly_id", "invoice_id", "invoice_number", "raw_shipment_reference", "carrier_id", "carrier_code", "issue_type", "is_anomaly", "expected_decision", "affected_entity_ids_json", "injection_method", "ground_truth_billed", "ground_truth_expected", "injected_variance", "details_json", "created_at"],
            "rows": [
                [gt.label_id, gt.anomaly_id, gt.invoice_id, gt.invoice_number, gt.raw_shipment_reference, gt.carrier_id, gt.carrier_code, gt.issue_type, gt.is_anomaly, gt.expected_decision, gt.affected_entity_ids_json, gt.injection_method, gt.ground_truth_billed, gt.ground_truth_expected, gt.injected_variance, gt.details_json, gt.created_at.isoformat()]
                for gt in gtls
            ]
        }

        # 18. Audit Events
        events = db.query(AuditEvent).order_by(AuditEvent.event_id).all()
        tables["audit_events"] = {
            "columns": ["event_id", "entity_type", "entity_id", "event_type", "actor", "payload_json", "notes", "timestamp"],
            "rows": [
                [ev.event_id, ev.entity_type, ev.entity_id, ev.event_type, ev.actor, ev.payload_json, ev.notes, ev.timestamp.isoformat()]
                for ev in events
            ]
        }

        # 19. Entity Status History
        histories = db.query(EntityStatusHistory).order_by(EntityStatusHistory.history_id).all()
        tables["entity_status_history"] = {
            "columns": ["history_id", "entity_name", "entity_id", "from_status", "to_status", "transition_reason", "changed_by", "changed_at"],
            "rows": [
                [sh.history_id, sh.entity_name, sh.entity_id, sh.from_status, sh.to_status, sh.transition_reason, sh.changed_by, sh.changed_at.isoformat()]
                for sh in histories
            ]
        }

        return tables

    def _write_csv(self, path: Path, columns: List[str], rows: List[List[Any]]):
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            writer.writerows(rows)

    def _write_json(self, path: Path, columns: List[str], rows: List[List[Any]]):
        records = [dict(zip(columns, row)) for row in rows]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, sort_keys=True)

    def _write_sql(self, path: Path, table_data: Dict[str, Dict[str, Any]]):
        with open(path, "w", encoding="utf-8") as f:
            f.write("-- Freight Invoice Validation System: Synthetic Seed Script\n")
            f.write("-- Generated deterministically with fixed epoch timestamps\n\n")

            for table_name, data in table_data.items():
                cols = ", ".join(data["columns"])
                for row in data["rows"]:
                    vals = []
                    for val in row:
                        if val is None:
                            vals.append("NULL")
                        elif isinstance(val, (int, float)):
                            vals.append(str(val))
                        elif isinstance(val, bool):
                            vals.append("1" if val else "0")
                        else:
                            escaped = str(val).replace("'", "''")
                            vals.append(f"'{escaped}'")
                    f.write(f"INSERT INTO {table_name} ({cols}) VALUES ({', '.join(vals)});\n")
                f.write("\n")
