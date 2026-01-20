#!/usr/bin/env bash

# Kraken2 Database builder script

# Description:
#   This script downloads the taxonomy -> library for Kraken2 then builds a custom database
#   for a specific domain(kingdom) like arachaea, bacteria, virus, protozoa etc.

# Usage:
#   ./kraken2_db.sh <database_type> <threads>
#   database_type - archaea, bacteria, 
#   threads - Number of CPU threads to use.

# Example:
#   bash kraken2_db.sh archaea 32


set -euo pipefail # Exit on error, undefined variables, and pipe failures

# Configuration section
# Database type is taken from the command like arguement $1. If not provided then it is set to archaea
DB_TYPE="${1:-archaea}"

# Number of threads to use
THREADS="${2:-8}"

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Project root is two levels up from scripts/kraken2_db_build/
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Set the database directory
DB_BASE_DIR="/home/chandru/myTMP/databases"

# Directoru for this specific database
DB_DIR="$DB_BASE_DIR/${DB_TYPE}_db"

# Log file for this build
LOG_FILE="$DB_BASE_DIR/${DB_TYPE}_build.log"


# Helper Functions

# Function to print the header section
print_header() {
    local message="$1"
    echo ""
    printf "=%.0s" {1..80} # =%.0s is a way of printing only "=" 80 times.
    echo ""
    echo "  $message"
    printf "=%.0s" {1..80}
    echo ""
}

# Function to print step information
print_step() {
    local step_num="$1"
    local total_steps="$2"
    local message="$3"
    echo ""
    echo "[$step_num/$total_steps] $message"
    echo "    Time: $(date '+%Y-%m-%d %H:%M:%S')"
}

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to calculate and display elapsed time
show_elapsed_time() {
    local start_time=$1
    local end_time=$(date +%s)
    local elapsed=$((end_time - start_time))
    local hours=$((elapsed / 3600))
    local minutes=$(( (elapsed % 3600) / 60 ))
    local seconds=$((elapsed % 60))
    echo "    Elapsed time: ${hours}h ${minutes}m ${seconds}s"
}


# Main Script

START_TIME=$(date +%s)

print_header "Kraken2 Database Build Script"
echo "Configuration:"
echo "  Database Type: $DB_TYPE"
echo "  Threads: $THREADS"
echo "  Database Directory: $DB_DIR"
echo "  Log File: $LOG_FILE"
echo "  Project Root: $PROJECT_ROOT"

# Initialize log file
{
    echo "Kraken2 Database Build Log"
    echo "Database Type: $DB_TYPE"
    echo "Started: $(date)"
} > $LOG_FILE

# Step 1 - Verify Dependencies

print_step 1 5 "Checking dependencies.."

if ! command_exists kraken2; then
    echo "Error: kraken2 is not installed or not in PATH"
    echo "Please install kraken2 using conda or module system"
    exit 1
fi

if ! command_exists kraken2-build; then
    echo "Error: kraken2 build is not installed."
    exit 1
fi

echo "  kraken2 found: $(which kraken2)"
echo "  kraken2 version: $(kraken2 --version 2>&1 | head -n1)"

# Step 2 - Create Database Directory

print_step 2 5 "Create database directory structure"

# Create main database directory
mkdir -p "$DB_DIR"
echo "  Created $DB_DIR"


# Step 3 - Download Taxonomy

print_step 3 5 "Download NCBI taxonomy database"

# Check if the taxonomy already exists
if [ -d "$DB_DIR/taxonomy" ] && [ -f "$DB_DIR/taxonomy/nodes.dmp" ]; then 
    echo "Taxonomy already exists, skipping download"
else
    echo "Downloading taxonomy files from NCBI..."
    echo "This may take 10-30 minutes.."

    STEP_START=$(date +%s)

    if kraken2-build --download-taxonomy --db "$DB_DIR" >> "$LOG_FILE" 2>&1; then
        echo "Taxonomy download complete sucessfully."
        show_elapsed_time $STEP_START
    else
        echo "Error: Taxonomy download failed. Check log: $LOG_FILE"
        exit 1
    fi
fi


# Step 4 - Download Library Data

print_step 4 5 "Downloading Library data for $DB_TYPE"

# Function to download a single library
download_library() {
    local lib_name="$1"
    local lib_dir="$DB_DIR/library/$lib_name"

    if [ -d "$lib_dir" ] && [ -n "$(ls -A "$lib_dir" 2>/dev/null)" ]; then
        echo "Library $lib_name already exists, skipping.."
        return 0
    else
        echo "Downloading library $lib_name"
        echo "This step may take several hours-days.."

        STEP_START=$(date +%s)

        if kraken2-build --download-library "$lib_name" \
            --db "$DB_DIR" \
            --threads "$THREADS" >> "$LOG_FILE" 2>&1; then
            echo "Library $lib_name downloaded sucessfully."
            show_elapsed_time $STEP_START
            return 0
        else
            echo "Error: Library $lib_name download failed. Check log $LOG_FILE"
            return 1
        
        fi
    fi
}

# Download librarues based on database type
case "$DB_TYPE" in 
    archaea)
        download_library "archaea" || exit 1
        ;;
    bacteria)
        download_library "bacteria" || exit 1
        ;;
    *)
        echo "Error. Unknown database $DB_TYPE"
        echo "Valid types are archaea, bacteria"
        exit 1
        ;;
esac

# Step 5 - Build Kraken2 Database

print_step 5 5 "Building Kraken2 Database"

# Check if the database already exists (hash.k2d is the key file we are looking for)
if [ -f "$DB_DIR/hash.k2d" ]; then
    echo "Database already built (hash.k2d) exists."
    echo "To re-build with different k-mer delete the $DB_DIR/hash.k2d file."

else
    echo "Building database index.."
    echo "This step can take like 2-10 hours, depends on the database size"
    echo "Progress is logged to - $LOG_FILE"

    BUILD_START=$(date +%s)

    if kraken2-build --build \
        --db "$DB_DIR" \
        --threads "$THREADS" >> "$LOG_FILE" 2>&1; then
        echo "Database build completed sucessfully."
        show_elapsed_time $BUILD_START
    else
        echo "Error: Database build failed. Check the log file $LOG_FILE"
        exit 1
    fi
fi

END_TIME=$(date +%s)

print_header "Build Complete!"

echo "Database Information:"
echo "  Type: $DB_TYPE"
echo "  Location: $DB_DIR"
echo "  Log File: $LOG_FILE"
echo ""

# Display database files
if [ -f "$DB_DIR/hash.k2d" ]; then
    echo "Database files:"
    ls -lh "$DB_DIR"/*.k2d 2>/dev/null || echo " No .k2d files found"
    echo ""

    # Show total database size
    DB_SIZE=$(du -sh "$DB_DIR" | cut -f1)
    echo "Total database size: $DB_SIZE"
fi

echo ""
show_elapsed_time $START_TIME

echo ""
echo "You can now use this database with Kraken2:"
echo "  kraken2 --db $DB_DIR --threads $THREADS input.fastq"
echo ""

# Log completion
{
    echo "================================="
    echo "Build completed: $(date)"
    echo "Total time: $((END_TIME - START_TIME)) seconds"
    echo "================================="
} >> "$LOG_FILE"

exit 0


# This much resource is enough for the script to run for archaea database in like 30 min.
# srun --partition=lu48 --cpus-per-task=6 --mem=24G --time=2:00:00 --pty bash
# Or else run the slumr script slurm_kraken2.sh.
