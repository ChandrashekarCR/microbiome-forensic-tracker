#!/bin/bash

################################################################################
# Bracken Database Builder - Build Bracken Database from Kraken2 Database
################################################################################
# Description:
#   After building a Kraken2 database, you need to build a Bracken database
#   for accurate abundance estimation. This script builds Bracken databases
#   for specified read lengths.
#
# Prerequisites:
#   - Kraken2 database must be built first
#   - Bracken must be installed in your conda environment
#
# Usage:
#   ./build_bracken_db.sh <database_type> <read_length> <threads>
#
#   database_type: archaea, bacteria, viral, etc. (must match kraken2 db)
#   read_length: 50, 75, 100, 150, 200, 250, 300 (default: 150)
#   threads: Number of CPU threads (default: 16)
#
# Example:
#   ./build_bracken_db.sh archaea 150 16
#   ./build_bracken_db.sh bacteria 100 32
#
# What this does:
#   Creates database files needed for Bracken abundance estimation.
#   For each read length, it builds: database<length>mers.kmer_distrib
#
# Author: Generated for LUNARC HPC
# Date: January 2026
################################################################################

set -euo pipefail

# =============================================================================
# CONFIGURATION
# =============================================================================

DB_TYPE="${1:-}"
READ_LENGTH="${2:-150}"
THREADS="${3:-16}"

# Get directories
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DB_DIR="$PROJECT_ROOT/kraken2_dbs/${DB_TYPE}_db"
LOG_FILE="$PROJECT_ROOT/kraken2_dbs/${DB_TYPE}_bracken.log"

# =============================================================================
# VALIDATION
# =============================================================================

# Check if database type provided
if [ -z "$DB_TYPE" ]; then
    echo "ERROR: Database type not specified"
    echo ""
    echo "Usage: $0 <database_type> [read_length] [threads]"
    echo ""
    echo "Examples:"
    echo "  $0 archaea 150 16"
    echo "  $0 bacteria 100 32"
    exit 1
fi

# Check if kraken2 database exists
if [ ! -d "$DB_DIR" ]; then
    echo "ERROR: Kraken2 database not found: $DB_DIR"
    echo ""
    echo "Build the Kraken2 database first using:"
    echo "  sbatch slurm_build_kraken2.sh"
    exit 1
fi

if [ ! -f "$DB_DIR/hash.k2d" ]; then
    echo "ERROR: Incomplete Kraken2 database: $DB_DIR"
    echo "The database must be fully built before creating Bracken database"
    exit 1
fi

# Validate read length
VALID_LENGTHS=(50 75 100 150 200 250 300)
if [[ ! " ${VALID_LENGTHS[@]} " =~ " ${READ_LENGTH} " ]]; then
    echo "ERROR: Invalid read length: $READ_LENGTH"
    echo "Valid lengths: ${VALID_LENGTHS[@]}"
    exit 1
fi

# Check if bracken-build exists
if ! command -v bracken-build &> /dev/null; then
    echo "ERROR: bracken-build not found"
    echo "Please install bracken in your conda environment:"
    echo "  conda install -c bioconda bracken"
    exit 1
fi

# =============================================================================
# BUILD BRACKEN DATABASE
# =============================================================================

echo "=========================================="
echo "Bracken Database Build"
echo "=========================================="
echo "Database: $DB_TYPE"
echo "Read length: $READ_LENGTH"
echo "Threads: $THREADS"
echo "Kraken2 DB: $DB_DIR"
echo "Log file: $LOG_FILE"
echo "Started: $(date)"
echo ""

# Check if already built
KMER_FILE="$DB_DIR/database${READ_LENGTH}mers.kmer_distrib"
if [ -f "$KMER_FILE" ]; then
    echo "⚠ Bracken database for read length $READ_LENGTH already exists"
    echo "File: $KMER_FILE"
    echo ""
    read -p "Rebuild? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Skipping build."
        exit 0
    fi
    echo "Rebuilding..."
fi

START_TIME=$(date +%s)

# Run bracken-build
echo "Building Bracken database..."
echo "This may take 1-4 hours depending on database size"
echo ""

{
    echo "================================="
    echo "Bracken Build Log"
    echo "Database: $DB_TYPE"
    echo "Read Length: $READ_LENGTH"
    echo "Started: $(date)"
    echo "================================="
} > "$LOG_FILE"

if bracken-build -d "$DB_DIR" -t "$THREADS" -k 35 -l "$READ_LENGTH" >> "$LOG_FILE" 2>&1; then
    END_TIME=$(date +%s)
    ELAPSED=$((END_TIME - START_TIME))
    
    echo "✓ Bracken database build completed successfully!"
    echo ""
    echo "Build time: $((ELAPSED / 3600))h $((ELAPSED % 3600 / 60))m $((ELAPSED % 60))s"
    echo ""
    echo "Created file: $KMER_FILE"
    
    if [ -f "$KMER_FILE" ]; then
        FILE_SIZE=$(du -h "$KMER_FILE" | cut -f1)
        echo "File size: $FILE_SIZE"
    fi
    
    echo ""
    echo "You can now use Bracken for abundance estimation:"
    echo "  bracken -d $DB_DIR -i sample_report.txt -o sample_bracken.txt -r $READ_LENGTH -l S"
    
    {
        echo "================================="
        echo "Build completed: $(date)"
        echo "Elapsed: $ELAPSED seconds"
        echo "================================="
    } >> "$LOG_FILE"
    
else
    echo "✗ ERROR: Bracken database build failed!"
    echo "Check log file: $LOG_FILE"
    exit 1
fi

echo ""
