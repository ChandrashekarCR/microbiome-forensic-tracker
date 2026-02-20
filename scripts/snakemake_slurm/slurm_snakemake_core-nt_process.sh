#!/bin/bash
#SBATCH --job-name=snakemake_kraken2
#SBATCH -A lu2025-2-11
#SBATCH --partition=gpua40
#SBATCH --cpus-per-task=36
#SBATCH --mem=400G
#SBATCH --time=6:00:00
#SBATCH --output=snakemake_kraken2_%j.out
#SBATCH --error=snakemake_kraken2_%j.err

set -euo pipefail

# Load environment
module load Anaconda3/2024.06-1
conda activate snakemake

# Navigate to directory
cd /home/chandru/binp51/

# Set snakemake configuration
export SNAKEMAKE_CORES=30
export SNAKEMAKE_JOBS=8

# Run snakemake with parallelization
snakemake \
    --snakefile workflow/Snakefile \
    --cores $SNAKEMAKE_CORES \
    --jobs $SNAKEMAKE_JOBS \
    --resources mem_mb=380000 \
    --latency-wait 50 \
    2>&1 | tee snakemake_run_$(date +%Y%m%d_%H%M%S).log

echo "Snakemake pipeline completed at $(date)"