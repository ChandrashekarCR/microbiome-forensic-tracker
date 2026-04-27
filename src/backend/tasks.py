"""
Celery tasks for running the Snakemake metagenomics pipeline.

This file defines the actual work that happens in the background.
When FastAPI calls run_pipeline.delay(...), the arguments are serialized
to JSON, pushed to Redis, and this function executes in the Celery worker.
"""

import csv
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import yaml
from celery.utils.log import get_task_logger

from backend.celery_app import celery_app
from backend.database import SyncSessionLocal
from backend.models import Abundance, Samples

logger = get_task_logger(__name__)

# Path to your project root (where Snakefile lives)
PROJECT_ROOT = Path("/home/chandru/binp51")
UPLOAD_DIR = PROJECT_ROOT / "uploads"  # ← MUST MATCH main.py UPLOAD_DIR
SNAKEFILE = PROJECT_ROOT / "workflow" / "Snakefile"
CONFIG_FILE = PROJECT_ROOT / "config" / "config_single_run.yaml"
PROFILE = PROJECT_ROOT / "profiles" / "single_run"
RESULTS_BASE = PROJECT_ROOT / "results"  # ← Use project results by default
RUNTIME_DIR = PROJECT_ROOT / "config" / "runtime"
TASK_LOGS_DIR = PROJECT_ROOT / "logs" / "celery_tasks"
SNAKEMAKE_BIN = "snakemake"  # assumes conda env is activated when worker starts

# Verify critical paths exist
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
TASK_LOGS_DIR.mkdir(parents=True, exist_ok=True)
RUNTIME_DIR.mkdir(parents=True, exist_ok=True)


# generate_sample_sheet(123214,"malmo_park2", "some_path1", "some_path2")


# This function is used in every API end point. It opens a database session, gives it to the endpoint and the closes it when done.
def _get_db():
    db = SyncSessionLocal()  # Opens the malmo_db database

    try:
        return db  # Give it whichever API endpoint needs it
    except Exception:
        db.close()  # Then close the database at the end afeter utilizing it.
        raise


def _update_status(db, sample_id: int, **kwargs):
    """
    Update a samples status and optional felds in the database

    """
    sample = db.query(Samples).filter(Samples.id == sample_id).first()
    if not sample:
        logger.error(f"Sample {sample_id} not found in database!")

    for key, value in kwargs.items():
        if hasattr(sample, key) and value is not None:
            setattr(sample, key, value)

    db.commit()
    db.refresh(sample)
    logger.info(f"[Sample {sample_id}] Status updated: {kwargs}")


def _import_abundance_csv(db, sample_id: str, sample_name: str, results_dir: str):
    """
    Parse the Bracken CSV output files and insert them into the Abundance SQL table.
    """
    reports_dir = Path(results_dir) / "11_final_reports"
    ranks = ["phylum", "class", "order", "family", "genus", "species"]

    for rank in ranks:
        csv_path = reports_dir / f"kraken_bracken_{rank}.csv"
        if not csv_path.exists():
            logger.warning(f"Abundance file missing: {csv_path}")
            continue

        with open(csv_path, newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)

            # Usually the columns are: classifier, clade, tax_id, <sample_name>
            # Let's dynamically get the 4th column name which holds the abundance value
            fieldnames = reader.fieldnames
            abundance_col = fieldnames[3]

            for row in reader:
                try:
                    abundance = Abundance(
                        sample_id=str(sample_id),
                        sample_name=sample_name,
                        classifier=row["classifier"],
                        clade=row["clade"],
                        taxa_id=int(row["tax_id"]),
                        rank=rank,
                        relative_abundance=float(row[abundance_col]),
                    )
                    db.add(abundance)
                except ValueError as e:
                    logger.warning(f"Skipping row due to data format error: {row}. Error: {e}")

        # Commit the transaction for each file/rank
        db.commit()
        logger.info(f"[{sample_name}] Successfully imported '{rank}' abundances into DB.")


def _generate_sample_sheet(sample_name: str, r1_path: str, r2_path: str) -> Path:
    """
    Write a per-sample TSV in the format helper_scripts.py expects:
    """
    sheets_dir = RUNTIME_DIR / "sample_sheets"
    sheets_dir.mkdir(parents=True, exist_ok=True)

    sheet_path = sheets_dir / f"{sample_name}.tsv"

    with open(sheet_path, "w", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["sample", "r1", "r2"])
        writer.writerow([sample_name, r1_path, r2_path])

    logger.info(f"Sample sheet written: {sheet_path}")
    return sheet_path


# Celery tasks
@celery_app.task(
    bind=True,
    name="run_pipeline",
    max_retries=1,
    default_retry=120,
)
def run_pipeline(self, sample_id: int, sample_name: str, r1_path: str, r2_path: str):
    """
    Run the full snakemake pipelin for one sample
    This funcitons excecutes inside the celery worker process.
    It blockes for 40 minutes while snakemake submits and monitors SLURM jobs
    FastAu returned 201 long before this starts
    """
    # Get the database
    db = _get_db()
    TASK_LOGS_DIR.mkdir(parents=True, exist_ok=True)

    try:
        # Step1: Mark as processing
        _update_status(db, sample_id, status="processing", started_at=datetime.now(timezone.utc))

        self.update_state(state="PROGRESS", meta={"step": "preparing", "sample": sample_name})

        # Step2: Generate the per-sample TSV
        sheet_path = _generate_sample_sheet(sample_name, r1_path, r2_path)

        # Step3: Build the snakemake command
        # snakemake --snakefile workflow/Snakefile \
        #   --profile profiles/single_run \
        #   --configfile config/config_single_run.yaml \
        #   --config samples_file=....
        #   per_sample_results=TRue

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = TASK_LOGS_DIR / f"{sample_name}_{timestamp}.log"

        snakemake_cmd = [
            SNAKEMAKE_BIN,
            "--snakefile",
            str(SNAKEFILE),
            "--profile",
            str(PROFILE),
            "--configfile",
            str(CONFIG_FILE),
            "--config",
            f"samples_file={sheet_path}",
            "per_sample_results=True",
        ]

        logger.info(f"[{sample_name}] Command: {' '.join(snakemake_cmd)}")

        self.update_state(state="PROGRESS", meta={"step": "snakemake_running", "sample": sample_name})

        # Step4: Run Snakemake
        with open(log_file, "w") as log_fh:
            result = subprocess.run(snakemake_cmd, cwd=str(PROJECT_ROOT), stdout=log_fh, stderr=subprocess.STDOUT, check=False)

        # Step5: CHeck the resutl
        if result.returncode != 0:
            with open(log_file) as lf:
                lines = lf.readlines()
            error_tail = "".join(lines[-50:])

            logger.error(f"[{sample_name}] FAILED (rc={result.returncode})")

            _update_status(
                db,
                sample_id,
                status="failed",
                error_msg=f"Exit code {result.returncode}:\n{error_tail}",
                log_path=str(log_file),
            )
            raise RuntimeError(f"Pipeline failed for {sample_name}")

        # Step6: Success
        logger.info(f"[{sample_name}] Pipeline completed!")

        # Compute the results directory (mirrors what Snakefile does)
        results_dir = os.path.join(
            str(CONFIG_FILE).replace("config_single_run.yaml", ""),
            "..",  # We'll read it properly
        )
        # The actual results dir is: config's results_dir + sample_name
        # Read it from the config to stay in sync
        with open(CONFIG_FILE) as cf:
            cfg = yaml.safe_load(cf)
        results_dir = os.path.join(cfg["data"]["results_dir"], sample_name)

        # Step7: Import the datafrom csv to sql table for malmo_backend database
        try:
            logger.info(f"[{sample_name}] Importing abundance CSVs to database")
            _import_abundance_csv(db, str(sample_id), sample_name, results_dir)
        except Exception as e:
            logger.error(f"[{sample_name}] Failed to import abundance data: {e}")
            _update_status(db, sample_id, status="failed", completed_at=datetime.now(timezone.utc), log_path=str(log_file))

        _update_status(
            db,
            sample_id,
            status="completed",
            completed_at=datetime.now(timezone.utc),
            log_path=str(log_file),
        )

        return {
            "sample_id": sample_id,
            "sample_name": sample_name,
            "status": "completed",
            "results_dir": results_dir,
        }

    except Exception as exc:
        logger.exception(f"[{sample_name}] Task error")
        try:
            _update_status(db, sample_id, status="failed", error_msg=str(exc)[:500])
        except Exception:
            pass
        raise

    finally:
        db.close()
