#!/bin/bash
#SBATCH --job-name=kraken2_archaea
#SBATCH --partition=lu48
#SBATCH --cpus-per-task=12
#SBATCH --mem=48G
#SBATCH --time=1:30:00
#SBATCH --output=kraken2_archaea_%j.out
#SBATCH --error=kraken2_archaea_%j.err

# Load modules and activate conda environment
module load Anaconda3/2024.06-1 
conda activate binp51_env

bash /home/chandru/binp51/scripts/kraken2_db_build/kraken2_db.sh archaea 12