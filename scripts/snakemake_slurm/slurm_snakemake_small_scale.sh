#!/bin/bash
#SBATCH --time=6:00:00

# Test the pipeline for a few samples. 5-10 samples

set -euo pipefail

# Configuration
PROFILE="profiles/small_scale"


# Load environment
module load Anaconda3/2024.06-1
conda activate snakemake

# Navigate to project
cd /home/chandru/binp51

# Create log directory
mkdir -p logs/test_runs

echo "Running dry-run validation..."
if snakemake --profile $PROFILE --dry-run --quiet; then
    echo "Dry-run passed"
else
    echo "Dry-run failed"
    exit 1
fi

echo "Starting test pipeline..."
snakemake \
    --profile $PROFILE \
    --cores 200 \
    --keep-going \
    2>&1 | tee logs/test_runs/test_run_$(date +%Y%m%d_%H%M%S).log

echo "Test completed at $(date)"