import subprocess
import csv
from pathlib import Path
from celery_app import celery_app
from database import SessionLocal
#import crud

# Path to your project root (where Snakefile lives)
PROJECT_ROOT = Path("/home/chandru/binp51")
SNAKEFILE    = PROJECT_ROOT / "workflow" / "Snakefile"
CONFIG_FILE  = PROJECT_ROOT / "config" / "config_single_run.yaml"
PROFILE      = PROJECT_ROOT / "profiles" / "single"
SAMPLE_SHEET = PROJECT_ROOT / "config" / "samples_single_run.tsv"


def generate_sample_sheet(sample_name: str, r1_path: str, r2_path: str):
    """
    Write a single-row TSV so Snakemake only processes this one sample.
    Pattern: config/samples_job_{job_id}.tsv.
    """
    SAMPLE_SHEET.parent.mkdir(parents=True, exist_ok=True)
    with open(SAMPLE_SHEET, "w", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["sample", "r1", "r2"])
        writer.writerow([sample_name, r1_path, r2_path])



generate_sample_sheet("malmo_park2","some_path1","some_path2")