import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app.core.database import Base
from backend.app.generator.generator import SyntheticDataGenerator
from backend.app.generator.exporter import DataExporter
import tempfile
from pathlib import Path

def test_seed_determinism_checksums():
    """
    Mandatory Rule: Two identical runs with the same seed and configuration
    must produce matching data checksums.
    """
    fixed_seed = 20261022

    # Run 1
    engine1 = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine1)
    db1 = sessionmaker(bind=engine1)()
    gen1 = SyntheticDataGenerator(seed=fixed_seed)
    gen1.generate_all(db1, num_carriers=5, num_shipments=20, num_invoices=15)

    dir1 = Path(tempfile.mkdtemp())
    exp1 = DataExporter(output_dir=str(dir1))
    res1 = exp1.export_all(db1)
    db1.close()

    # Run 2
    engine2 = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine2)
    db2 = sessionmaker(bind=engine2)()
    gen2 = SyntheticDataGenerator(seed=fixed_seed)
    gen2.generate_all(db2, num_carriers=5, num_shipments=20, num_invoices=15)

    dir2 = Path(tempfile.mkdtemp())
    exp2 = DataExporter(output_dir=str(dir2))
    res2 = exp2.export_all(db2)
    db2.close()

    # Compare checksums
    assert res1["file_checksums"] == res2["file_checksums"]
    for filename in res1["file_checksums"]:
        assert res1["file_checksums"][filename] == res2["file_checksums"][filename]
