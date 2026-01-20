#!/bin/bash
#SBATCH --job-name=kraken2_bacteria
#SBATCH --partition=lu48
#SBATCH --cpus-per-task=36
#SBATCH --mem=200G
#SBATCH --time=2-00:00:00
#SBATCH --output=kraken2_bacteria_%j.out
#SBATCH --error=kraken2_bacteria_%j.err

# Load the environment
module load Anaconda3/2024.06-1 
conda activate binp51_env

# Run the script
bash /home/chandru/binp51/scripts/kraken2_db_build/kraken2_db.sh bacteria 36