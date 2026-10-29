"""
Automated Reproducibility Verification Pipeline (Phase 5).
Executes dual-run generation with identical seeds across separate database sessions,
verifying 100% bit-for-bit equivalence in row counts, deterministic IDs, exports, and SHA-256 checksums.
"""

import os
import shutil
from pathlib import Path
from typing import Dict, Any, List
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.database import Base
from backend.app.generator.generator import SyntheticDataGenerator
from backend.app.generator.exporter import DataExporter


class ReproducibilityVerifier:
    """
    Executes automated dual-run determinism and reproducibility verification.
    """

    @classmethod
    def verify(
        cls,
        profile_name: str = "starter",
        seed: int = 20261022,
        base_dir: str = "data/test_reproducibility"
    ) -> Dict[str, Any]:
        base_path = Path(base_dir)
        run1_dir = base_path / "run_1"
        run2_dir = base_path / "run_2"

        # Clean old runs
        if base_path.exists():
            shutil.rmtree(base_path, ignore_errors=True)

        run1_dir.mkdir(parents=True, exist_ok=True)
        run2_dir.mkdir(parents=True, exist_ok=True)

        # -------------------------------------------------------------
        # Execution 1
        # -------------------------------------------------------------
        engine1 = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(bind=engine1)
        Session1 = sessionmaker(bind=engine1)
        db1 = Session1()

        gen1 = SyntheticDataGenerator(profile_name=profile_name, seed=seed)
        counts1 = gen1.generate_all(db1)

        exporter1 = DataExporter(output_dir=str(run1_dir))
        export_res1 = exporter1.export_all(db1, seed=seed)
        checksums1 = export_res1["file_checksums"]
        db1.close()

        # -------------------------------------------------------------
        # Execution 2
        # -------------------------------------------------------------
        engine2 = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(bind=engine2)
        Session2 = sessionmaker(bind=engine2)
        db2 = Session2()

        gen2 = SyntheticDataGenerator(profile_name=profile_name, seed=seed)
        counts2 = gen2.generate_all(db2)

        exporter2 = DataExporter(output_dir=str(run2_dir))
        export_res2 = exporter2.export_all(db2, seed=seed)
        checksums2 = export_res2["file_checksums"]
        db2.close()

        # -------------------------------------------------------------
        # Verification & Comparison
        # -------------------------------------------------------------
        mismatches: List[str] = []

        # 1. Compare Entity Counts
        for entity, cnt1 in counts1.items():
            cnt2 = counts2.get(entity, -1)
            if cnt1 != cnt2:
                mismatches.append(f"Entity count mismatch for {entity}: Run 1={cnt1}, Run 2={cnt2}")

        # 2. Compare File Checksums (Bit-for-bit)
        all_files = sorted(set(checksums1.keys()).union(set(checksums2.keys())))
        for rel_file in all_files:
            hash1 = checksums1.get(rel_file)
            hash2 = checksums2.get(rel_file)
            if hash1 != hash2:
                mismatches.append(f"Hash mismatch on {rel_file}: Run 1={hash1}, Run 2={hash2}")

        is_reproducible = (len(mismatches) == 0)

        # Clean temporary test output
        shutil.rmtree(base_path, ignore_errors=True)

        return {
            "reproducible": is_reproducible,
            "seed": seed,
            "profile": profile_name,
            "files_compared": len(all_files),
            "entities_compared": len(counts1),
            "mismatches_count": len(mismatches),
            "mismatches": mismatches,
            "checksums_sample": {k: checksums1[k] for k in list(checksums1.keys())[:5]}
        }
