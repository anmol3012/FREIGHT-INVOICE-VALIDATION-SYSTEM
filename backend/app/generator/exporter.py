import csv
import json
import hashlib
from pathlib import Path
from typing import Dict, Any, List
from sqlalchemy.orm import Session

from backend.app.models.carrier import Carrier
from backend.app.models.rate_card import RateCard, RateLane, AccessorialRule
from backend.app.models.shipment import Shipment, WeightMeasurement, AccessorialEvent, DeliveryRecord
from backend.app.models.invoice import InvoiceHeader, InvoiceLine
from backend.app.models.exception import InvoiceException
from backend.app.models.credit_note import CreditNote
from backend.app.models.ground_truth import GroundTruthLabel

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

    def export_all(self, db: Session) -> Dict[str, Any]:
        checksums = {}

        # 1. Export CSVs
        csv_files = self._export_csv(db)
        for name, path in csv_files.items():
            checksums[f"csv/{path.name}"] = self.calculate_file_sha256(path)

        # 2. Export JSON
        json_files = self._export_json(db)
        for name, path in json_files.items():
            checksums[f"json/{path.name}"] = self.calculate_file_sha256(path)

        # 3. Export SQL
        sql_path = self._export_sql(db)
        checksums[f"sql/{sql_path.name}"] = self.calculate_file_sha256(sql_path)

        # 4. Write checksums.sha256 manifest
        manifest_path = self.output_dir / "checksums.sha256"
        with open(manifest_path, "w", encoding="utf-8") as f:
            for rel_path, h in sorted(checksums.items()):
                f.write(f"{h}  {rel_path}\n")

        return {
            "output_directory": str(self.output_dir),
            "manifest_file": str(manifest_path),
            "file_checksums": checksums
        }

    def _export_csv(self, db: Session) -> Dict[str, Path]:
        files = {}

        # Carriers
        carriers = db.query(Carrier).order_by(Carrier.id).all()
        p = self.csv_dir / "carriers.csv"
        with open(p, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "carrier_code", "name", "tax_id", "payment_terms_days", "status", "contact_email"])
            for c in carriers:
                writer.writerow([c.id, c.carrier_code, c.name, c.tax_id, c.payment_terms_days, c.status, c.contact_email])
        files["carriers"] = p

        # Shipments
        shipments = db.query(Shipment).order_by(Shipment.id).all()
        p = self.csv_dir / "shipments.csv"
        with open(p, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "bol_number", "carrier_id", "origin_zip", "origin_city", "origin_state", "destination_zip", "destination_city", "destination_state", "distance_miles", "dock_type", "status"])
            for s in shipments:
                writer.writerow([s.id, s.bol_number, s.carrier_id, s.origin_zip, s.origin_city, s.origin_state, s.destination_zip, s.destination_city, s.destination_state, s.distance_miles, s.dock_type, s.status])
        files["shipments"] = p

        # Invoices
        invoices = db.query(InvoiceHeader).order_by(InvoiceHeader.id).all()
        p = self.csv_dir / "invoices.csv"
        with open(p, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "invoice_number", "carrier_id", "bol_number_billed", "invoice_date", "due_date", "total_billed_amount", "calculated_expected_amount", "total_variance_amount", "status", "validation_status", "is_duplicate"])
            for inv in invoices:
                writer.writerow([inv.id, inv.invoice_number, inv.carrier_id, inv.bol_number_billed, inv.invoice_date, inv.due_date, inv.total_billed_amount, inv.calculated_expected_amount, inv.total_variance_amount, inv.status, inv.validation_status, inv.is_duplicate])
        files["invoices"] = p

        # Invoice Lines
        lines = db.query(InvoiceLine).order_by(InvoiceLine.id).all()
        p = self.csv_dir / "invoice_lines.csv"
        with open(p, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "invoice_id", "line_number", "charge_type", "charge_code", "description", "billed_units", "billed_rate", "billed_amount", "expected_units", "expected_rate", "expected_amount", "variance_amount", "status"])
            for l in lines:
                writer.writerow([l.id, l.invoice_id, l.line_number, l.charge_type, l.charge_code, l.description, l.billed_units, l.billed_rate, l.billed_amount, l.expected_units, l.expected_rate, l.expected_amount, l.variance_amount, l.status])
        files["invoice_lines"] = p

        # Ground Truth
        gts = db.query(GroundTruthLabel).order_by(GroundTruthLabel.id).all()
        p = self.csv_dir / "ground_truth_labels.csv"
        with open(p, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "invoice_id", "invoice_number", "bol_number", "carrier_code", "scenario_type", "is_anomaly", "expected_verdict", "ground_truth_billed", "ground_truth_expected", "injected_variance"])
            for g in gts:
                writer.writerow([g.id, g.invoice_id, g.invoice_number, g.bol_number, g.carrier_code, g.scenario_type, g.is_anomaly, g.expected_verdict, g.ground_truth_billed, g.ground_truth_expected, g.injected_variance])
        files["ground_truth_labels"] = p

        return files

    def _export_json(self, db: Session) -> Dict[str, Path]:
        files = {}

        # Master & Rates JSON
        carriers = db.query(Carrier).all()
        carriers_data = []
        for c in carriers:
            rc_list = []
            for rc in c.rate_cards:
                rc_list.append({
                    "code": rc.rate_card_code,
                    "model": rc.base_rate_model,
                    "min_charge": rc.minimum_charge_floor,
                    "lanes": [{"origin": l.origin_zip_prefix, "dest": l.dest_zip_prefix, "cwt": l.base_rate_cwt, "mile": l.base_rate_per_mile} for l in rc.lanes]
                })
            rules_list = [{"code": r.code, "rate_type": r.rate_type, "unit_rate": r.unit_rate, "free_time": r.free_time_minutes} for r in c.accessorial_rules]
            carriers_data.append({
                "carrier_code": c.carrier_code,
                "name": c.name,
                "terms_days": c.payment_terms_days,
                "rate_cards": rc_list,
                "accessorial_rules": rules_list
            })

        p = self.json_dir / "master_carrier_rates.json"
        with open(p, "w", encoding="utf-8") as f:
            json.dump(carriers_data, f, indent=2, default=str)
        files["master_rates"] = p

        # Invoices Summary JSON
        invoices = db.query(InvoiceHeader).all()
        inv_data = [{
            "invoice_number": inv.invoice_number,
            "carrier_id": inv.carrier_id,
            "bol": inv.bol_number_billed,
            "date": str(inv.invoice_date),
            "billed": inv.total_billed_amount,
            "expected": inv.calculated_expected_amount,
            "variance": inv.total_variance_amount,
            "status": inv.status,
            "validation_status": inv.validation_status
        } for inv in invoices]

        p = self.json_dir / "invoices_reconciled.json"
        with open(p, "w", encoding="utf-8") as f:
            json.dump(inv_data, f, indent=2)
        files["invoices"] = p

        return files

    def _export_sql(self, db: Session) -> Path:
        p = self.sql_dir / "seed_data.sql"
        with open(p, "w", encoding="utf-8") as f:
            f.write("-- Freight Invoice Validation System: Seed Data SQL Dump\n")
            f.write("-- Deterministic Seed Export\n\n")

            carriers = db.query(Carrier).order_by(Carrier.id).all()
            for c in carriers:
                f.write(f"INSERT INTO carriers (id, carrier_code, name, tax_id, payment_terms_days, status, contact_email) "
                        f"VALUES ({c.id}, '{c.carrier_code}', '{c.name}', '{c.tax_id}', {c.payment_terms_days}, '{c.status}', '{c.contact_email}');\n")

            f.write("\n-- End Carrier Master\n")
        return p
