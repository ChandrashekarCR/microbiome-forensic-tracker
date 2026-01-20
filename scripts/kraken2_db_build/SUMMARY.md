# Kraken2 Database Build Scripts - Complete Summary

## 📦 What You Have Now

I've created a complete, production-ready suite of scripts for building Kraken2 databases on the LUNARC HPC system. Here's what's included:

### Scripts Created

1. **build_kraken2_db.sh** - Core database building script
   - Handles downloading taxonomy and libraries
   - Builds Kraken2 database index
   - Includes error handling and progress tracking
   - Can resume interrupted downloads

2. **slurm_build_kraken2.sh** - SLURM job script for single database
   - Properly configured for LUNARC COSMOS cluster
   - Activates conda environment automatically
   - Allocates appropriate resources (32 cores, 224 GB RAM)
   - Generates detailed log files

3. **slurm_build_all_databases.sh** - SLURM array job for multiple databases
   - Builds multiple databases in parallel
   - Each database gets its own compute node
   - More efficient than separate submissions

4. **build_bracken_db.sh** - Bracken database builder
   - Builds Bracken databases after Kraken2 is complete
   - Needed for abundance estimation
   - Supports multiple read lengths

5. **check_db_status.sh** - Status monitoring tool
   - Shows summary of all databases
   - Detailed information per database
   - Checks completion status, size, etc.

### Documentation Created

1. **README.md** - Comprehensive documentation (17 KB)
   - Detailed explanations of every component
   - Step-by-step instructions
   - LUNARC-specific guidance
   - Troubleshooting guide

2. **QUICK_REFERENCE.md** - Quick command reference
   - Common commands and workflows
   - Time/resource estimates
   - Troubleshooting quick fixes
   - Configuration templates

## 🎯 How Everything Works Together

### The Workflow

```
1. Edit Configuration
   └─> slurm_build_kraken2.sh (set DB_TYPE, threads, etc.)

2. Submit to SLURM
   └─> sbatch slurm_build_kraken2.sh
   
3. SLURM Allocates Resources
   └─> Gets compute node with 32 cores, 224 GB RAM
   
4. SLURM Activates Conda
   └─> Sources conda and activates nf_env
   
5. SLURM Runs Build Script
   └─> build_kraken2_db.sh archaea 32
   
6. Build Script Executes Steps:
   ├─> Download taxonomy (NCBI nodes.dmp, names.dmp)
   ├─> Download library (genomic sequences for archaea)
   ├─> Build database (creates hash.k2d, opts.k2d, taxo.k2d)
   └─> Clean up (removes intermediate files)
   
7. Optional: Build Bracken DB
   └─> ./build_bracken_db.sh archaea 150 16

8. Monitor Progress
   ├─> squeue -u $USER
   ├─> tail -f logs/kraken2_build_<JOBID>.out
   └─> ./check_db_status.sh
```

## 🔍 Understanding LUNARC SLURM Directives

### Resource Allocation Explained

```bash
#SBATCH -N 1                    # Request 1 compute node
#SBATCH --ntasks-per-node=1     # Run 1 process on that node
#SBATCH -c 32                   # Allocate 32 CPU cores to that process
#SBATCH --mem-per-cpu=7000      # 7000 MB (7 GB) per core
                                # Total RAM = 32 × 7 GB = 224 GB
```

**Why these values?**
- **32 cores**: Kraken2-build uses multi-threading effectively
- **224 GB RAM**: Bacteria database build needs ~200 GB at peak
- **48 hours walltime**: Bacteria download + build can take 24-48 hours

### COSMOS Cluster Specifics

- Each COSMOS node has **48 cores** and **254 GB RAM**
- Default memory: **5300 MB per core** (254 GB ÷ 48 cores)
- By requesting **7000 MB per core**, you use more memory but fewer cores
- LUNARC will charge you for **idle cores** if you exceed default memory

### Job States

- **PD (Pending)**: Waiting for resources to become available
- **R (Running)**: Currently executing on a compute node
- **CG (Completing)**: Finishing up, cleaning temporary files
- **CD (Completed)**: Successfully finished
- **F (Failed)**: Job encountered an error
- **TO (Timeout)**: Exceeded walltime limit

## 📊 What Each Database Contains

### Taxonomy (Shared by All Databases)
- **nodes.dmp**: Parent-child relationships between taxonomic IDs
- **names.dmp**: Scientific and common names for each taxon
- **Size**: ~500 MB
- **Download time**: 10-30 minutes
- **Only downloaded once**, then shared across all databases

### Library (Organism-Specific)

**Archaea Library** (~5 GB):
- Complete genomes of archaeal species from NCBI RefSeq
- ~400-500 genomes
- Representative species from all archaeal phyla

**Bacteria Library** (~300 GB):
- Complete bacterial genomes from NCBI RefSeq
- ~100,000+ genomes (and growing!)
- Includes all major bacterial groups
- **Largest download** - takes 12-24 hours

**Viral Library** (~3 GB):
- Viral genomes and sequences
- ~15,000 viral species
- Includes DNA and RNA viruses

### Database Index Files

After building, three files are created:

1. **hash.k2d**: Hash table mapping k-mers to taxonomic IDs
   - Largest file (~80-90% of database size)
   - Fast k-mer lookup during classification

2. **opts.k2d**: Database options and parameters
   - Small file (<1 MB)
   - Stores k-mer length, minimizer settings

3. **taxo.k2d**: Taxonomic tree structure
   - Medium file (~100-500 MB)
   - Compressed taxonomy for quick traversal

## 🔧 Key Design Features

### 1. Robustness
- **Error handling**: Scripts exit on any error (`set -euo pipefail`)
- **Resume capability**: Checks if steps are complete before re-running
- **Validation**: Verifies dependencies before starting

### 2. Monitoring
- **Progress tracking**: Each step reports timing and status
- **Detailed logging**: Both SLURM logs and build logs
- **Status checker**: Quick overview of all databases

### 3. Flexibility
- **Configurable resources**: Easy to adjust cores, memory, time
- **Multiple database types**: Archaea, bacteria, viral, fungi, etc.
- **Array jobs**: Build multiple databases in parallel

### 4. LUNARC Integration
- **Conda activation**: Properly sources conda for SLURM environment
- **Resource requests**: Optimized for COSMOS cluster
- **Log management**: Organized output files

## 📝 Step-by-Step: What Happens When You Submit

### Before Submission
1. You edit `slurm_build_kraken2.sh` to set:
   - `DB_TYPE="archaea"` (or bacteria, viral, etc.)
   - `CONDA_ENV_NAME="nf_env"` (your conda environment)
   - `THREADS=32` (number of cores to use)

### Submission
```bash
sbatch slurm_build_kraken2.sh
```
- SLURM assigns a job ID (e.g., 123456)
- Job enters queue with status **PD (Pending)**

### Resource Allocation
- SLURM finds an available node with 32 cores and 224 GB RAM
- When found, job status changes to **R (Running)**
- You get a specific node (e.g., cosmos3-42)

### Job Execution on Compute Node

**1. Environment Setup** (< 1 minute)
- Script sources conda initialization
- Activates your conda environment (`nf_env`)
- Verifies kraken2 and kraken2-build are available

**2. Taxonomy Download** (10-30 minutes)
- Checks if `$DB_DIR/taxonomy/` exists
- If not, downloads from NCBI FTP:
  ```
  taxonomy/
  ├── nodes.dmp      (parent-child relationships)
  ├── names.dmp      (taxonomic names)
  ├── merged.dmp     (merged taxon IDs)
  └── delnodes.dmp   (deleted taxon IDs)
  ```

**3. Library Download** (1-24 hours, depending on database)
- For archaea: Downloads archaeal RefSeq genomes
- Uses rsync to NCBI servers
- Creates: `library/archaea/library.fna` and metadata
- Shows progress in log file

**4. Database Build** (1-24 hours)
- Processes FASTA files into k-mer database
- Creates hash table (hash.k2d)
- Builds taxonomy tree (taxo.k2d)
- Saves options (opts.k2d)
- **Most CPU/memory intensive step**

**5. Cleanup** (5-15 minutes)
- Removes intermediate files
- Keeps only final .k2d files and library
- Saves 50-70% disk space

**6. Completion**
- Job status becomes **CG (Completing)**
- Final logs written
- Job status becomes **CD (Completed)**

### Output Files

After completion, you have:

```
kraken2_dbs/
└── archaea_db/
    ├── hash.k2d              # Main database (~5 GB)
    ├── opts.k2d              # Options (~1 KB)
    ├── taxo.k2d              # Taxonomy (~100 MB)
    ├── taxonomy/             # NCBI taxonomy
    │   ├── nodes.dmp
    │   └── names.dmp
    └── library/              # Downloaded sequences
        └── archaea/
            └── library.fna

logs/
├── kraken2_build_123456.out  # Standard output
└── kraken2_build_123456.err  # Errors (if any)

kraken2_dbs/
└── archaea_build.log         # Detailed build log
```

## 🚀 Quick Start (Step by Step)

### Step 1: Navigate and Setup
```bash
cd /home/chandru/binp51/scripts/kraken2_db_build
mkdir -p logs
```

### Step 2: Choose Your Approach

**Option A: Build One Database First (Recommended)**
```bash
# Edit the configuration
nano slurm_build_kraken2.sh

# Find these lines and modify:
DB_TYPE="archaea"              # Start with archaea (smaller, faster)
CONDA_ENV_NAME="nf_env"        # Your conda environment name
THREADS=32                     # Keep as-is

# Save and exit (Ctrl+X, then Y, then Enter)

# Submit the job
sbatch slurm_build_kraken2.sh

# You'll see: Submitted batch job 123456
```

**Option B: Build Multiple Databases in Parallel**
```bash
# Edit the array job script
nano slurm_build_all_databases.sh

# Find the DATABASES array and modify:
DATABASES=(
    "archaea"
    "bacteria"
    "viral"
)

# Update array size to match (currently set to --array=0-2 for 3 databases)

# Submit
sbatch slurm_build_all_databases.sh
```

### Step 3: Monitor Progress
```bash
# Check job status
squeue -u $USER

# View output in real-time (replace 123456 with your job ID)
tail -f logs/kraken2_build_123456.out

# Check detailed status
./check_db_status.sh

# For specific database
./check_db_status.sh archaea
```

### Step 4: Wait for Completion
- **Archaea**: 2-4 hours
- **Bacteria**: 24-48 hours
- **Viral**: 1-3 hours

### Step 5: Verify Success
```bash
# Check status
./check_db_status.sh archaea

# Should show:
# ✓ Database: COMPLETE
# ✓ Taxonomy: Downloaded
# ✓ Libraries: archaea

# Verify files exist
ls -lh /home/chandru/binp51/kraken2_dbs/archaea_db/*.k2d
```

### Step 6: (Optional) Build Bracken Database
```bash
# Build Bracken database for 150bp reads
./build_bracken_db.sh archaea 150 16

# For bacteria with 100bp reads
./build_bracken_db.sh bacteria 100 32
```

### Step 7: Use Your Database
```bash
# Classify a sample
kraken2 \
  --db /home/chandru/binp51/kraken2_dbs/archaea_db \
  --threads 16 \
  --output sample_kraken.txt \
  --report sample_report.txt \
  sample_R1.fastq sample_R2.fastq

# Estimate abundances with Bracken
bracken \
  -d /home/chandru/binp51/kraken2_dbs/archaea_db \
  -i sample_report.txt \
  -o sample_bracken.txt \
  -r 150 \
  -l S \
  -t 10
```

## ⚠️ Important Notes

### Don't Do These Things

1. **Don't run on login node**: Always use SLURM for database building
2. **Don't underestimate time**: Bacteria takes 24-48 hours, not 2-4 hours
3. **Don't forget disk space**: Check available space before starting
4. **Don't cancel during build**: The build phase can't resume if interrupted

### Do These Things

1. **Check disk space first**: `df -h /home/chandru/binp51`
2. **Start with small databases**: Archaea or viral for testing
3. **Monitor regularly**: Use `./check_db_status.sh`
4. **Keep logs**: They're invaluable for troubleshooting
5. **Use array jobs**: More efficient for multiple databases

## 📚 Files Reference

| File | Purpose | When to Use |
|------|---------|-------------|
| `build_kraken2_db.sh` | Core build logic | Called by SLURM scripts, or run locally for testing |
| `slurm_build_kraken2.sh` | Single database SLURM job | Build one database at a time |
| `slurm_build_all_databases.sh` | Multiple databases (array job) | Build several databases in parallel |
| `build_bracken_db.sh` | Bracken database builder | After Kraken2 DB is complete |
| `check_db_status.sh` | Status monitoring | Anytime you want to check progress |
| `README.md` | Full documentation | For detailed explanations and troubleshooting |
| `QUICK_REFERENCE.md` | Command cheat sheet | For quick command lookup |

## 🎓 Learning Resources

- **LUNARC Basics**: https://lunarc-documentation.readthedocs.io/en/latest/getting_started/login_howto/
- **SLURM Job Submission**: https://lunarc-documentation.readthedocs.io/en/latest/manual/submitting_jobs/manual_basic_job/
- **Kraken2 Manual**: https://github.com/DerrickWood/kraken2/wiki/Manual
- **Bracken Tutorial**: https://github.com/jenniferlu717/Bracken

## 🆘 Support

- **LUNARC Support**: support@lunarc.lu.se (for cluster/SLURM issues)
- **Kraken2 Issues**: https://github.com/DerrickWood/kraken2/issues
- **Bracken Issues**: https://github.com/jenniferlu717/Bracken/issues

---

**You're all set!** 🎉

Start with building the archaea database to test the system, then move on to bacteria and other databases as needed. Good luck with your metagenomics analysis!
