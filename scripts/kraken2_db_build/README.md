# Kraken2 Database Build Scripts for LUNARC HPC

This directory contains scripts to build Kraken2 databases on the LUNARC COSMOS HPC cluster. The scripts are designed to download taxonomy data, library sequences, and build custom Kraken2 databases for metagenomics analysis.

## 📁 Directory Structure

```
scripts/kraken2_db_build/
├── README.md                          # This file
├── build_kraken2_db.sh                # Main bash script for database building
├── slurm_build_kraken2.sh             # SLURM script for single database
├── slurm_build_all_databases.sh       # SLURM array script for multiple databases
└── logs/                              # Directory for SLURM output logs (auto-created)

kraken2_dbs/                           # Created automatically in project root
├── archaea_db/                        # Archaea database
│   ├── hash.k2d                       # Main database file
│   ├── opts.k2d                       # Options file
│   ├── taxo.k2d                       # Taxonomy file
│   ├── taxonomy/                      # NCBI taxonomy
│   └── library/                       # Downloaded sequences
├── bacteria_db/                       # Bacteria database
├── viral_db/                          # Viral database
└── logs/                              # Build logs
```

## 🔧 Prerequisites

### 1. Conda Environment Setup

First, create a conda environment with kraken2 and bracken:

```bash
# Create a new conda environment
conda create -n nf_env python=3.9

# Activate the environment
conda activate nf_env

# Install kraken2 and bracken from bioconda
conda install -c bioconda kraken2 bracken

# Verify installation
kraken2 --version
bracken -v
```

### 2. LUNARC Account Setup

- Ensure you have an active LUNARC account
- Check your project allocation: `projinfo`
- If you have multiple projects, note your project code (format: `lu2024-x-xxx`)

## 📝 Script Descriptions

### 1. `build_kraken2_db.sh` - Main Build Script

This is the core bash script that performs the actual database building.

**What it does:**
1. **Checks dependencies** - Verifies kraken2 is installed
2. **Creates directories** - Sets up the database directory structure
3. **Downloads taxonomy** - Gets NCBI taxonomy files (nodes.dmp, names.dmp, etc.)
4. **Downloads library** - Downloads genomic sequences for specified organisms
5. **Builds database** - Creates the kraken2 index files (hash.k2d, opts.k2d, taxo.k2d)
6. **Cleans up** - Removes intermediate files to save disk space

**Usage:**
```bash
# Make executable
chmod +x build_kraken2_db.sh

# Build archaea database with 16 threads
./build_kraken2_db.sh archaea 16

# Build bacteria database with 32 threads
./build_kraken2_db.sh bacteria 32

# Build combined archaea+bacteria database
./build_kraken2_db.sh combined 32
```

**Available database types:**
- `archaea` - Archaeal genomes (~1-5 GB)
- `bacteria` - Bacterial genomes (~100-400 GB, takes longest!)
- `viral` - Viral genomes (~1-2 GB)
- `fungi` - Fungal genomes (~10-50 GB)
- `plant` - Plant genomes (~50-200 GB)
- `protozoa` - Protozoan genomes (~5-20 GB)
- `combined` - Archaea + Bacteria

**Time estimates:**
- Archaea: 2-4 hours
- Bacteria: 24-48 hours (largest database!)
- Viral: 1-3 hours
- Combined: 30-50 hours

### 2. `slurm_build_kraken2.sh` - SLURM Job Script

This script submits a single database build job to the SLURM scheduler on LUNARC.

**How SLURM works on LUNARC:**

SLURM (Simple Linux Utility for Resource Management) is the job scheduler used on LUNARC clusters. Instead of running jobs directly on the login node (which is forbidden!), you submit jobs to SLURM which allocates compute nodes for your work.

**Key SLURM directives explained:**

```bash
#SBATCH -J kraken2_build          # Job name (shown in squeue)
#SBATCH -t 48:00:00                # Maximum runtime (HH:MM:SS)
                                   # Job will be killed if it exceeds this!
                                   
#SBATCH -N 1                       # Number of nodes (1 node for this job)
#SBATCH --ntasks-per-node=1        # Number of processes per node
#SBATCH -c 32                      # CPUs per task (32 cores)
#SBATCH --mem-per-cpu=7000         # Memory per CPU in MB
                                   # Total: 32 cores × 7000 MB = 224 GB

#SBATCH -o logs/kraken2_%j.out     # Standard output file
#SBATCH -e logs/kraken2_%j.err     # Standard error file
                                   # %j is replaced with job ID

#SBATCH --no-requeue               # Don't restart if node fails
```

**Important LUNARC-specific information:**

- **COSMOS nodes** have 48 cores and 254 GB RAM per node
- **Default memory** per core is 5300 MB (if you don't specify)
- **Maximum walltime** is 168 hours (7 days)
- **If you request more memory per core**, you're charged for idle cores
- **Email notifications** require your email address (uncomment those lines)

**Before submitting:**

1. **Edit the CONFIGURATION section** in the script:
   ```bash
   DB_TYPE="archaea"              # Change to: bacteria, viral, etc.
   CONDA_ENV_NAME="nf_env"        # Your conda environment name
   THREADS=32                     # Match the -c value above
   ```

2. **If you have multiple projects**, uncomment and edit:
   ```bash
   #SBATCH -A lu2024-x-xxx        # Replace with your project code
   ```

3. **For email notifications**, uncomment and edit:
   ```bash
   #SBATCH --mail-user=your.email@lu.se
   #SBATCH --mail-type=END,FAIL
   ```

**Submit the job:**

```bash
# Navigate to the script directory
cd /home/chandru/binp51/scripts/kraken2_db_build

# Create logs directory
mkdir -p logs

# Submit the job
sbatch slurm_build_kraken2.sh

# You'll see output like:
# Submitted batch job 123456
```

**Monitor your job:**

```bash
# Check job status
squeue -u $USER

# View detailed job info
scontrol show job 123456

# Check output in real-time (replace 123456 with your job ID)
tail -f logs/kraken2_build_123456.out

# Check for errors
tail -f logs/kraken2_build_123456.err

# Cancel a job if needed
scancel 123456
```

**Job states in squeue:**
- `PD` (Pending) - Waiting for resources
- `R` (Running) - Currently executing
- `CG` (Completing) - Finishing up
- `CD` (Completed) - Finished successfully
- `F` (Failed) - Job failed
- `TO` (Timeout) - Exceeded walltime

### 3. `slurm_build_all_databases.sh` - Array Job Script

This script uses **SLURM job arrays** to build multiple databases in parallel. This is much more efficient than submitting separate jobs!

**What are job arrays?**

A job array lets you run multiple similar jobs with one submission. LUNARC will allocate multiple nodes simultaneously, and each array task runs independently.

**How it works:**

```bash
#SBATCH --array=0-2    # Creates 3 array tasks: indices 0, 1, 2

# In the script:
DATABASES=("archaea" "bacteria" "viral")

# Task 0 builds: archaea
# Task 1 builds: bacteria  
# Task 2 builds: viral
```

**Advantages:**
- ✅ All databases build simultaneously (if resources available)
- ✅ Single submission command
- ✅ Easier to manage and monitor
- ✅ Separate log files for each database

**Customize for your needs:**

To build different databases, edit the array:

```bash
# Example 1: Build 5 databases
DATABASES=(
    "archaea"
    "bacteria"
    "viral"
    "fungi"
    "protozoa"
)
#SBATCH --array=0-4    # Update this to 0-4 (5 tasks)

# Example 2: Just bacteria and archaea
DATABASES=(
    "bacteria"
    "archaea"
)
#SBATCH --array=0-1    # Update this to 0-1 (2 tasks)
```

**Submit array job:**

```bash
sbatch slurm_build_all_databases.sh
```

**Monitor array jobs:**

```bash
# View all array tasks
squeue -u $USER

# You'll see output like:
# JOBID    PARTITION  NAME           USER     ST  TIME  NODES
# 123456_0 lu         kraken2_array  chandru  R   2:30  1
# 123456_1 lu         kraken2_array  chandru  R   2:30  1
# 123456_2 lu         kraken2_array  chandru  PD  0:00  1

# Cancel all tasks in array
scancel 123456

# Cancel specific array task (e.g., task 1)
scancel 123456_1

# Check logs for each task
tail -f logs/kraken2_array_123456_0.out  # archaea
tail -f logs/kraken2_array_123456_1.out  # bacteria
tail -f logs/kraken2_array_123456_2.out  # viral
```

## 🚀 Quick Start Guide

### Option 1: Build a Single Database (Recommended for first time)

```bash
# 1. Navigate to the scripts directory
cd /home/chandru/binp51/scripts/kraken2_db_build

# 2. Make scripts executable
chmod +x *.sh

# 3. Create logs directory
mkdir -p logs

# 4. Edit the SLURM script configuration
nano slurm_build_kraken2.sh
# Change: DB_TYPE="archaea"  (or bacteria, viral, etc.)
# Change: CONDA_ENV_NAME="nf_env"  (your conda env name)

# 5. Submit the job
sbatch slurm_build_kraken2.sh

# 6. Monitor progress
squeue -u $USER
tail -f logs/kraken2_build_<JOBID>.out
```

### Option 2: Build Multiple Databases in Parallel

```bash
# 1. Navigate to the scripts directory
cd /home/chandru/binp51/scripts/kraken2_db_build

# 2. Edit the array script
nano slurm_build_all_databases.sh
# Modify DATABASES array to include desired databases
# Update --array parameter to match array size

# 3. Submit array job
sbatch slurm_build_all_databases.sh

# 4. Monitor all tasks
squeue -u $USER
```

### Option 3: Run Locally (Not Recommended for Large Databases)

Only use this for testing or small databases like viral/archaea:

```bash
# Activate your conda environment
conda activate nf_env

# Run the build script directly
cd /home/chandru/binp51/scripts/kraken2_db_build
./build_kraken2_db.sh archaea 8
```

⚠️ **WARNING**: Do NOT run large database builds (especially bacteria) on the login node! You will get your account suspended.

## 📊 Resource Requirements

### Disk Space

Databases require significant disk space:

| Database | Download Size | Final Size | Build Time (32 cores) |
|----------|--------------|------------|----------------------|
| Archaea  | 2-5 GB       | 3-8 GB     | 2-4 hours           |
| Bacteria | 100-300 GB   | 200-500 GB | 24-48 hours         |
| Viral    | 1-3 GB       | 2-5 GB     | 1-3 hours           |
| Fungi    | 10-30 GB     | 20-60 GB   | 4-8 hours           |
| Combined | 150-350 GB   | 250-600 GB | 30-50 hours         |

### Memory Requirements

The script requests:
- **32 cores × 7000 MB/core = 224 GB total memory**

This is sufficient for most databases. The bacteria database build can use up to 200+ GB RAM.

### CPU Requirements

More cores = faster builds:
- **8 cores**: Suitable for small databases (archaea, viral)
- **16 cores**: Good balance for medium databases
- **32 cores**: Recommended for bacteria or combined databases

## 📖 Understanding the Build Process

### Step-by-Step Breakdown

#### Step 1: Download Taxonomy
```bash
kraken2-build --download-taxonomy --db <database_dir>
```
- Downloads NCBI taxonomy database
- Files: nodes.dmp (parent-child relationships), names.dmp (scientific names)
- Size: ~500 MB
- Time: 10-30 minutes (network dependent)
- **This is shared across all databases** - only needs to be downloaded once

#### Step 2: Download Library
```bash
kraken2-build --download-library archaea --db <database_dir> --threads 32
```
- Downloads genomic sequences from NCBI
- For bacteria, this downloads ~100,000+ genomes!
- Uses rsync to get FASTA files
- **This is the slowest step** (hours to days for bacteria)
- Network interruptions can be resumed

#### Step 3: Build Database
```bash
kraken2-build --build --db <database_dir> --threads 32
```
- Builds hash table and k-mer index
- Creates three files: hash.k2d, opts.k2d, taxo.k2d
- CPU-intensive and memory-intensive
- Uses all specified threads
- Cannot be resumed if interrupted

#### Step 4: Clean Up
```bash
kraken2-build --clean --db <database_dir>
```
- Removes intermediate files
- Saves significant disk space (50-70% reduction)
- Keeps only the final .k2d files needed for classification

## 🔍 Troubleshooting

### Job won't start (stays in PD state)

**Reason**: Insufficient resources available

**Solutions**:
```bash
# Check why job is pending
squeue -u $USER --start

# Reduce requested resources
#SBATCH -t 24:00:00     # Reduce walltime
#SBATCH -c 16           # Reduce cores
#SBATCH --mem-per-cpu=5300  # Use default memory
```

### Job fails with "Out of Memory" error

**Reason**: Database build needs more RAM

**Solution**: Increase memory request
```bash
#SBATCH --mem-per-cpu=10000  # 10 GB per core
# Note: You'll be charged for idle cores!
```

### Download interrupted/failed

**Reason**: Network issues or NCBI server problems

**Solution**: The script automatically resumes! Just resubmit:
```bash
# Resubmit the same job
sbatch slurm_build_kraken2.sh

# The script checks if files exist and skips completed steps
```

### Conda environment not found

**Error**: `ERROR: Failed to activate environment: nf_env`

**Solution**: 
```bash
# Check available environments
conda env list

# Update CONDA_ENV_NAME in the script to match your environment name
nano slurm_build_kraken2.sh
```

### Database files not found after build

**Check**:
```bash
# Navigate to database directory
cd /home/chandru/binp51/kraken2_dbs/archaea_db

# List files
ls -lh

# You should see:
# hash.k2d  opts.k2d  taxo.k2d

# Check build log
cat /home/chandru/binp51/kraken2_dbs/archaea_build.log
```

### Job killed before completion

**Reason**: Exceeded walltime

**Solution**: Increase time limit
```bash
#SBATCH -t 72:00:00  # 72 hours for bacteria database
```

## 📝 Best Practices

### 1. Start Small
- Build archaea or viral database first to test the pipeline
- Once successful, proceed to larger databases

### 2. Monitor Disk Space
```bash
# Check available space in your project directory
df -h /home/chandru/binp51

# Check database size during build
du -sh /home/chandru/binp51/kraken2_dbs/*
```

### 3. Use Job Arrays for Efficiency
- Build multiple databases simultaneously
- Better resource utilization
- Easier to manage

### 4. Keep Logs
- Always save SLURM output logs
- Check logs if job fails
- Logs contain timing information and error messages

### 5. Test Queue for Quick Tests
```bash
# For testing the script with small databases
#SBATCH --qos=test
#SBATCH -t 01:00:00
# Only use for actual testing, not production!
```

## 🎯 Using Your Databases

After successful build, use your databases for classification:

```bash
# Activate conda environment
conda activate nf_env

# Run kraken2 classification
kraken2 \
  --db /home/chandru/binp51/kraken2_dbs/archaea_db \
  --threads 16 \
  --output sample1_kraken.txt \
  --report sample1_report.txt \
  sample1_R1.fastq sample1_R2.fastq

# Run bracken for abundance estimation
bracken \
  -d /home/chandru/binp51/kraken2_dbs/archaea_db \
  -i sample1_report.txt \
  -o sample1_bracken.txt \
  -l S \
  -t 10
```

### SLURM Script for Kraken2 Classification

You can also create a SLURM script for running classifications:

```bash
#!/bin/bash
#SBATCH -J kraken2_classify
#SBATCH -t 04:00:00
#SBATCH -c 16
#SBATCH --mem-per-cpu=5300

conda activate nf_env

kraken2 \
  --db /home/chandru/binp51/kraken2_dbs/archaea_db \
  --threads 16 \
  --output ${SAMPLE}_kraken.txt \
  --report ${SAMPLE}_report.txt \
  ${SAMPLE}_R1.fastq ${SAMPLE}_R2.fastq
```

## 📚 Additional Resources

### LUNARC Documentation
- Main documentation: https://lunarc-documentation.readthedocs.io/
- Job submission guide: https://lunarc-documentation.readthedocs.io/en/latest/manual/submitting_jobs/manual_basic_job/
- SLURM quick reference: https://lunarc-documentation.readthedocs.io/en/latest/manual/manual_quick_reference/

### Kraken2 Documentation
- Official manual: https://github.com/DerrickWood/kraken2/wiki
- Building custom databases: https://github.com/DerrickWood/kraken2/wiki/Manual#custom-databases

### SLURM Commands Reference
```bash
squeue -u $USER           # View your jobs
squeue -u $USER --start   # See when pending jobs will start
scontrol show job JOBID   # Detailed job info
scancel JOBID             # Cancel a job
sacct -j JOBID            # Job accounting info after completion
sinfo                     # Cluster status
```

## 🆘 Getting Help

If you encounter issues:

1. **Check the logs** first:
   - SLURM output: `logs/kraken2_build_<JOBID>.out`
   - SLURM errors: `logs/kraken2_build_<JOBID>.err`
   - Build log: `kraken2_dbs/<dbtype>_build.log`

2. **Contact LUNARC support**:
   - Email: support@lunarc.lu.se
   - Include your job ID and error messages

3. **Kraken2 specific issues**:
   - GitHub issues: https://github.com/DerrickWood/kraken2/issues
   - Check if taxonomy/library downloads are working

## ⚖️ License & Citation

If you use these databases in your research, please cite:

**Kraken2**:
- Wood, D.E., Lu, J. & Langmead, B. Improved metagenomic analysis with Kraken 2. Genome Biol 20, 257 (2019). https://doi.org/10.1186/s13059-019-1891-0

**LUNARC**:
- Acknowledge LUNARC in your publications according to their guidelines

---

**Created**: January 2026  
**Author**: Generated for LUNARC HPC COSMOS cluster  
**Contact**: support@lunarc.lu.se (for LUNARC issues)
