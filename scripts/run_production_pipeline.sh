#!/bin/bash

################################################################################
# Production Pipeline Launcher for LUNARC
################################################################################
# This script submits the Snakemake pipeline as a SLURM job for full automation
# Usage: sbatch scripts/run_production_pipeline.sh
################################################################################

#SBATCH --job-name=snakemake_controller
#SBATCH -A lu2025-2-11
#SBATCH --partition=lu48
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=72:00:00
#SBATCH --output=logs/controller_%j.out
#SBATCH --error=logs/controller_%j.err

set -euo pipefail

# Load environment
module load Anaconda3/2024.06-1
conda activate snakemake

# Navigate to project directory
cd /home/chandru/binp51

# Create log directory
mkdir -p logs/slurm

# Run production pipeline
echo "Starting production pipeline at $(date)"
echo "Processing all 330 samples..."

# Run with production profile
snakemake \
    --profile profiles/production \
    --cores 500 \
    --keep-going \
    --rerun-incomplete \
    2>&1 | tee logs/production_run_$(date +%Y%m%d_%H%M%S).log

echo "Pipeline completed at $(date)"

# Generate summary report
echo "Generating summary report..."
python scripts/generate_pipeline_summary.py