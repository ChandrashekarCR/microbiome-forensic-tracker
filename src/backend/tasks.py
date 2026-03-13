import subprocess
import csv
from pathlib import Path
from celery_app import celery_app
from database import SessionLocal
import crud

# Path to your project root (where Snakefile lives)
PROJECT_ROOT = Path("/home/chandru/binp51")
SNAKEFILE    = PROJECT_ROOT / "workflow" / "Snakefile"
CONFIG_FILE  = PROJECT_ROOT / "config" / "config_single_run.yaml"
PROFILE      = PROJECT_ROOT / "profiles" / "single"
SAMPLE_SHEET = PROJECT_ROOT / "config" / "samples_single_run.tsv"


def generate_sample_sheet(sample_name: str, r1_path: str, r2_path: str):
    """
    Write a single-row TSV so Snakemake only processes this one sample.
    Overwrites the file each time (single job at a time with this approach).
    """
    SAMPLE_SHEET.parent.mkdir(parents=True, exist_ok=True)
    with open(SAMPLE_SHEET, "w", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["sample", "r1", "r2"])
        writer.writerow([sample_name, r1_path, r2_path])


@celery_app.task(bind=True, name="run_snakemake_pipeline")
def run_snakemake_pipeline(self, job_id: int, sample_name: str,
                           r1_path: str, r2_path: str):
    """
    Celery task:
    1. Generate single-sample TSV
    2. Run Snakemake with the single profile
    3. Update job status in DB
    """
    db = SessionLocal()

    try:
        # Update status → running
        crud.update_sample_status(db, job_id, "running")

        # Generate single-sample sheet
        generate_sample_sheet(sample_name, r1_path, r2_path)

        # Build Snakemake command
        cmd = [
            "snakemake",
            "--snakefile", str(SNAKEFILE),
            "--configfile", str(CONFIG_FILE),
            "--profile",   str(PROFILE),
            "--rerun-incomplete",
            "--nolock",
        ]

        # Run Snakemake as a subprocess
        result = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),   # Run from project root
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            crud.update_sample_status(db, job_id, "pass")
        else:
            crud.update_sample_status(db, job_id, "fail",
                                      error_msg=result.stderr[-2000:])  # last 2000 chars
            print(f"[Job {job_id}] STDERR:\n{result.stderr}")

    except Exception as e:
        crud.update_sample_status(db, job_id, "fail", error_msg=str(e))
        raise  # Re-raise so Celery marks the task as FAILED

    finally:
        db.close()

    return {"job_id": job_id, "status": "pass"}