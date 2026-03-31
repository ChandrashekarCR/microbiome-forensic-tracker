import csv
from pathlib import Path

# import crud

# Path to your project root (where Snakefile lives)
PROJECT_ROOT = Path("/home/chandru/binp51")
SNAKEFILE = PROJECT_ROOT / "workflow" / "Snakefile"
CONFIG_FILE = PROJECT_ROOT / "config" / "config_single_run.yaml"
PROFILE = PROJECT_ROOT / "profiles" / "single"
CONFIG_DIR = PROJECT_ROOT / "config"


def generate_sample_sheet(job_id: int, sample_name: str, r1_path: str, r2_path: str):
    """
    Write a UNIQUE sample sheet per job.
    This prevents race conditions when multiple jobs run simultaneously.

    Pattern: config/samples_job_{job_id}.tsv
    """
    # Create unique filename per job
    sample_sheet_path = CONFIG_DIR / f"samples_job_{job_id}.tsv"

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    with open(sample_sheet_path, "w", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["sample", "r1", "r2"])
        writer.writerow([sample_name, r1_path, r2_path])

    print(f"[Job {job_id}] Generated sample sheet: {sample_sheet_path}")
    return sample_sheet_path


generate_sample_sheet("malmo_park2", "some_path1", "some_path2")
