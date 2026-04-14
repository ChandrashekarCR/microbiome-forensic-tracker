"""
Celery tasks for running the Snakemake metagenomics pipeline.

This file defines the actual work that happens in the background.
When FastAPI calls run_pipeline.delay(...), the arguments are serialized
to JSON, pushed to Redis, and this function executes in the Celery worker.
"""

import os
import subprocess
import csv
from pathlib import Path

from backend.database import SyncSessionLocal
import logging
from pathlib import Path
from datetime import datetime, timezone

import yaml
from celery import states
from celery.utils.log import get_task_logger

from backend.celery_app import celery_app
from backend.models import Samples

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


#generate_sample_sheet(123214,"malmo_park2", "some_path1", "some_path2")

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
        if hasattr(sample,key) and value is not None:
            setattr(sample, key, value)
    
    db.commit()
    db.refresh(sample)
    logger.info(f"[Sample {sample_id}] Status updated: {kwargs}")

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

def _write_config_override(sample_name: str) -> tuple[Path, Path]:
    """
    Generate a per-sample config override YAML.

    WHY THIS IS NECESSARY:
    Your rules (fastqc_raw, fastp, etc.) resolve input files as:
        os.path.join(DATA_DIR, f"{w.sample}_R1.fastq.gz")

    DATA_DIR = config["data"]["raw_dir"]. So we MUST set raw_dir to the
    uploads/ directory where FastAPI saved the FASTQ files.

    We also set results_dir to a per-sample subdirectory so concurrent
    pipeline runs don't write to the same output folder.

    Snakemake merges this with config_single_run.yaml — only the keys
    we specify here are overridden. Everything else (tools, databases,
    parameters, resources) stays the same.
    """
    configs_dir = RUNTIME_DIR / "configs"
    configs_dir.mkdir(parents=True, exist_ok=True)

    # Each sample gets its own results subdirectory
    sample_results_dir = RESULTS_BASE / sample_name
    sample_results_dir.mkdir(parents=True, exist_ok=True)

    override = {
        "data": {
            "raw_dir": str(UPLOAD_DIR) + "/",       # WHERE FASTQ FILES ARE
            "results_dir": str(sample_results_dir) + "/",  # WHERE OUTPUTS GO
        },
        "samples": {
            "max_samples": 1,  # Only process this one sample
        },
    }

    config_path = configs_dir / f"{sample_name}_override.yaml"
    with open(config_path, "w") as f:
        yaml.dump(override, f, default_flow_style=False)

    logger.info(f"Config override written: {config_path}")
    return config_path, sample_results_dir

# Celery tasks
@celery_app.task(bind=True, name= "run_pipeline", max_retries=1, default_retry=120,)
def run_pipeline(self,sample_id: int, sample_name:str, r1_path: str, r2_path: str):
    """
    Run the full snakemake pipelin for one sample
    This funcitons excecutes inside the celery worker process.
    It blockes for 40 minutes while snakemake submits and monitors SLURM jobs
    FastAu returned 201 long before this starts
    """
    # Get the database
    db = _get_db()
    TASK_LOGS_DIR.mkdir(parents=True,exist_ok=True)

    try:
        # Step1: Mark as processing
        _update_status(db,sample_id,status="processing",started_at=datetime.now(timezone.utc)) 

        self.update_state(state='PROGRESS',meta={'step':'preparing','sample': sample_name})

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
            "--snakefile", str(SNAKEFILE),
            "--profile", str(PROFILE),
            "--configfile", str(CONFIG_FILE),
            "--config", f"samples_file={sheet_path}",
            "per_sample_results=True"
        ]

        logger.info(f"[{sample_name}] Command: {' '.join(snakemake_cmd)}")

        self.update_state(
            state="PROGRESS",
            meta={"step":"snakemake_running","sample":sample_name}
        )

        # Step4: Run Snakemake
        with open(log_file, "w") as log_fh:
            result = subprocess.run(snakemake_cmd,cwd=str(PROJECT_ROOT),stdout=log_fh,stderr=subprocess.STDOUT,check=False)
        
        # Step5: CHeck the resutl
        if result.returncode != 0:
            with open(log_file) as lf:
                lines = lf.readlines()
            error_tail = "".join(lines[-50:])

            logger.error(f"[{sample_name}] FAILED (rc={result.returncode})")

            _update_status(
                db, sample_id,
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
            ".."  # We'll read it properly
        )
        # The actual results dir is: config's results_dir + sample_name
        # Read it from the config to stay in sync
        with open(CONFIG_FILE) as cf:
            cfg = yaml.safe_load(cf)
        results_dir = os.path.join(cfg["data"]["results_dir"], sample_name)

        _update_status(
            db, sample_id,
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