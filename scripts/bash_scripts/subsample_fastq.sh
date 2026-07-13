#!/bin/bash
# Subsample 10 random FASTQ pairs from Malmo dataset for testing
# Usage: bash scripts/subsample_fastq.sh

set -euo pipefail

# Activate your conda environment
CONDA_ENV_NAME="binp51_env"  # CORRECTED: Changed from binp51_env to binp51

# Check if seqtk is available
if ! command -v seqtk &> /dev/null; then
    echo "INFO: seqtk not found, attempting to activate conda env..."
    eval "$(conda shell.bash hook)"
    conda activate "$CONDA_ENV_NAME"
fi

# Final check for seqtk
if ! command -v seqtk &> /dev/null; then
    echo "ERROR: seqtk could not be found even after activating conda env '$CONDA_ENV_NAME'."
    echo "Please ensure 'seqtk' is installed in that environment."
    exit 1
fi


# Configuration
SOURCE_DIR="/lunarc/nobackup/projects/snic2019-34-3/shared_elhaik_lab1/Projects/Microbiome/Malmo2025/fastq_files"
TARGET_DIR="/home/chandru/binp51/data/malmo_samples/01_fastq_test_samples"
NUM_SAMPLES=10
NUM_READS=100000  # Subsample to 100k reads per file (adjust as needed)

# Create target directory
mkdir -p "$TARGET_DIR"

echo "=== Subsampling FASTQ files for testing ==="
echo "Source: $SOURCE_DIR"
echo "Target: $TARGET_DIR"
echo "Samples: $NUM_SAMPLES"
echo "Reads per file: $NUM_READS"
echo "Tool: $(command -v seqtk)"
echo ""

# Find all R1 files using a more robust method
# This avoids issues with too many files for `ls`
R1_FILES=()
while IFS= read -r -d $'\0'; do
    R1_FILES+=("$REPLY")
done < <(find "$SOURCE_DIR" -maxdepth 1 -name '*_R1.fastq.gz' -print0 | head -z -n "$NUM_SAMPLES")


if [ ${#R1_FILES[@]} -eq 0 ]; then
    echo "ERROR: No R1 files found in $SOURCE_DIR matching '*_R1.fastq.gz'"
    exit 1
fi

# Process each sample
for R1 in "${R1_FILES[@]}"; do
    # Get sample name and R2 file
    SAMPLE=$(basename "$R1" _R1.fastq.gz)
    R2="${R1/_R1.fastq.gz/_R2.fastq.gz}"
    
    # Check if R2 exists
    if [ ! -f "$R2" ]; then
        echo "WARNING: R2 file not found for $SAMPLE, skipping..."
        continue
    fi
    
    echo "Processing: $SAMPLE"
    
    # Subsample R1 (same seed for reproducibility)
    seqtk sample -s100 "$R1" "$NUM_READS" | gzip -c > "$TARGET_DIR/${SAMPLE}_R1.fastq.gz"
    
    # Subsample R2 (same seed to keep pairs synchronized)
    seqtk sample -s100 "$R2" "$NUM_READS" | gzip -c > "$TARGET_DIR/${SAMPLE}_R2.fastq.gz"
    
    echo "Created ${SAMPLE}_R1.fastq.gz (${NUM_READS} reads)"
done

echo ""
echo "=== Subsampling complete ==="
echo "Output directory: $TARGET_DIR"
ls -lh "$TARGET_DIR" | head -10
echo ""
du -sh "$TARGET_DIR"