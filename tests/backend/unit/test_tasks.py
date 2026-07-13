"""
Unit tests for helper functions in `backend/tasks.py`.

We do NOT test the Celery task itself (`run_pipeline`) end-to-end — that
would need a real Snakemake install, a SLURM cluster and Redis.  Instead
we test its pure helpers in isolation:

    * generate_sample_sheet   — writes a TSV
    * render_snakemake_profile — copies + expands env vars
    * import_abundance_csv    — parses CSV rows into DB rows

For the last one we use a real SQLAlchemy sync session pointed at
in-memory SQLite (a different flavour of what `db_session` does for
async code).
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.backend import tasks
from src.backend.database import Base
from src.backend.models import Abundance, Samples



# generate_sample_sheet

class TestGenerateSampleSheet:

    def test_writes_expected_header_and_row(self, tmp_path, monkeypatch):
        # Redirect the sample-sheet output directory so the test is hermetic.
        monkeypatch.setattr(tasks, "RUNTIME_DIR", tmp_path)

        sheet = tasks.generate_sample_sheet(
            sample_name="malmo_01",
            r1_path="/data/malmo_01_R1.fq.gz",
            r2_path="/data/malmo_01_R2.fq.gz",
        )

        assert sheet.exists()
        rows = list(csv.reader(sheet.open(), delimiter="\t"))
        assert rows[0] == ["sample", "r1", "r2"]
        assert rows[1] == ["malmo_01", "/data/malmo_01_R1.fq.gz", "/data/malmo_01_R2.fq.gz"]



# render_snakemake_profile

class TestRenderSnakemakeProfile:

    def test_expands_environment_variables(self, tmp_path, monkeypatch):
        # Prepare a fake profile directory with a config.yaml that references
        # an environment variable.
        profile_dir = tmp_path / "profile_x"
        profile_dir.mkdir()
        (profile_dir / "config.yaml").write_text("kraken_db: ${TEST_KRAKEN_DB}\n")

        monkeypatch.setenv("TEST_KRAKEN_DB", "/mnt/kraken2/db_v1")
        monkeypatch.setattr(tasks, "RENDERED_PROFILES_DIR", tmp_path / "rendered")
        (tmp_path / "rendered").mkdir()

        rendered = tasks.render_snakemake_profile(profile_dir)
        content = (rendered / "config.yaml").read_text()

        assert "/mnt/kraken2/db_v1" in content
        assert "${TEST_KRAKEN_DB}" not in content



# import_abundance_csv

class TestImportAbundanceCsv:
    """
    Uses a synchronous in-memory SQLite session (the task helper is
    synchronous because Celery workers run outside asyncio).
    """

    @pytest.fixture
    def sync_session(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        session = Session()
        try:
            yield session
        finally:
            session.close()
            engine.dispose()

    def _build_results_dir(self, tmp_path: Path, bracken_csv: Path) -> Path:
        reports = tmp_path / "results" / "11_final_reports"
        reports.mkdir(parents=True)
        (reports / "kraken_bracken_species.csv").write_text(bracken_csv.read_text())
        return tmp_path / "results"

    def test_inserts_rows_from_csv(self, sync_session, tmp_path, bracken_csv_path):
        # Seed the parent sample so the FK is satisfiable (we don't actually
        # enforce FK on SQLite by default, but this mirrors production).
        parent = Samples(
            sample_name="malmo_01",
            username="alice",
            email="alice@e.c",
            r1_path="/tmp/r1",
            r2_path="/tmp/r2",
        )
        sync_session.add(parent)
        sync_session.commit()
        sync_session.refresh(parent)

        results_dir = self._build_results_dir(tmp_path, bracken_csv_path)

        tasks.import_abundance_csv(
            sync_session,
            sample_id=str(parent.id),
            sample_name="malmo_01",
            results_dir=str(results_dir),
        )

        rows = sync_session.query(Abundance).all()
        assert len(rows) == 5
        assert {r.clade for r in rows} == {
            "Bacteroides fragilis",
            "Prevotella copri",
            "Faecalibacterium prausnitzii",
            "Escherichia coli",
            "Akkermansia muciniphila",
        }
        assert all(r.rank == "species" for r in rows)

    def test_silently_skips_missing_rank_files(self, sync_session, tmp_path, bracken_csv_path):
        # Only species file exists; genus/phylum/etc. are absent.  Function
        # must log a warning and continue, not raise.
        results_dir = self._build_results_dir(tmp_path, bracken_csv_path)
        tasks.import_abundance_csv(
            sync_session,
            sample_id="s-1",
            sample_name="malmo_01",
            results_dir=str(results_dir),
        )
        rows = sync_session.query(Abundance).all()
        assert len(rows) == 5  # only species was present