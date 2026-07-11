# Microbiome Forensic Tracker  

[![CI/CD pipeline](https://github.com/ChandrashekarCR/microbiome-forensic-tracker/workflows/CI%2FCD%20pipeline/badge.svg)](https://github.com/ChandrashekarCR/microbiome-forensic-tracker/actions/workflows/ci.yaml) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE) [![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/) [![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff) [![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black) [![Snakemake](https://img.shields.io/badge/snakemake-%E2%89%A77-brightgreen.svg)](https://snakemake.readthedocs.io) [![GitHub issues](https://img.shields.io/github/issues/ChandrashekarCR/microbiome-forensic-tracker)](https://github.com/ChandrashekarCR/microbiome-forensic-tracker/issues) [![GitHub last commit](https://img.shields.io/github/last-commit/ChandrashekarCR/microbiome-forensic-tracker)](https://github.com/ChandrashekarCR/microbiome-forensic-tracker/commits)

**Microbiome Forensic Tracker (MFT)** is an end-to-end metagenomics workflow designed for forensic geolocation analysis. It takes paired-end shotgun sequencing reads, performs comprehensive bioinformatics processing, and uses machine learning to predict the geographic origin (latitude/longitude) of the sample based on its microbiome. Key features include rigorous data **quality control**, **host DNA removal**, **taxonomic profiling** (Kraken2 + Bracken), contig **assembly** (MEGAHIT) and **DNABERT-S embeddings**, all orchestrated through a reproducible [Snakemake](https://snakemake.readthedocs.io/) pipeline. The project includes both the data processing engine and a REST API backend (FastAPI) for result tracking and on-demand prediction. MFT is scalable across HPC (Slurm) and cloud (Azure) environments.

## Pipeline Workflow

MFT executes a multi-stage pipeline when given raw FASTQ data. The main stages are:

- **Quality Control:**  Run FastQC on raw reads, and aggregate with MultiQC.
- **Preprocessing:**  Trim/filter reads with *fastp* and remove adapters with *AdapterRemoval*.
- **Host-read Depletion:**  Align against a host genome (e.g. human) using *Bowtie2* to remove contaminant reads.
- **Error Correction:**  Correct sequencing errors using BBMap tools (`repair.sh`, `tadpole.sh`, or fallback `bbduk.sh`).
- **Taxonomic Classification:**  Classify reads with *Kraken2* and estimate abundances with *Bracken* at multiple taxonomic ranks.
- **Postprocessing:**  Normalize and standardize Bracken outputs, then merge per-sample abundance tables by taxonomic rank.
- **Assembly:**  Assemble filtered reads into contigs using *MEGAHIT*.
- **Sequence Embeddings:**  Generate **DNABERT-S** embeddings from assembled contigs (deep-learning-based sequence representations).

Each of these stages is defined as a Snakemake rule in `workflow/`, allowing parallel and incremental execution. The outputs are organized under the configured `results/` directory in numbered subfolders for each stage.  

 *Figure: Example output visualization from the pipeline. The charts illustrate a sample’s microbial abundance profiles and the geolocation prediction (latitude/longitude) with confidence scores.*  

## Outputs

Upon completion, MFT produces a structured set of output files for each sample:

- **QC Reports:** `qc_raw/` and `qc_processed/` contain FastQC HTML reports for raw and filtered reads, and a MultiQC summary.
- **Taxonomic Profiles:** `kraken/` and `bracken/` contain Kraken2 reports and Bracken abundance tables (in standard format).
- **Merged Tables:** `bracken_merged/` holds merged abundance matrices across samples, by rank (phylum, class, … species).
- **Assembly:** `assembly/` contains assembled contigs (FASTA) and assembly logs from MEGAHIT.
- **Embeddings:** `embeddings/` contains generated DNABERT-S embedding files for each contig sequence.
- **Feature Tables:** Feature-engineered tables (e.g., ecological diversity metrics) as CSV for model training.
- **Predictions:** A table of machine learning predictions (latitude, longitude) for each sample.

The **API/backend** also logs information in a PostgreSQL database (or SQLite for local testing), including sample metadata and final abundance tables used for prediction.

## Requirements

The workflow runs on Linux with the following requirements:

- **Python 3.9+** with `snakemake>=7`.
- **Apptainer/Singularity** (for containerized tools) or local tool installations.
- **SLURM** (for HPC profiles) or **Azure Batch** (for cloud).
- External tools (via containers in `bin/`): FastQC, fastp, AdapterRemoval, Bowtie2, Samtools, BBMap, Kraken2, Bracken, MEGAHIT, etc.
- (Optional) GPU drivers if running DNABERT-S on GPU.

Python dependencies are managed via `pyproject.toml`. Optional extra groups include:
- `dev` (linters, test tools),
- `snakemake` (workflow dependencies),
- `dnaberts` (for embeddings),
- `rag` (if using Retrieval-Augmented features),
- `backend` (FastAPI server).

## Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/ChandrashekarCR/microbiome-forensic-tracker.git
   cd microbiome-forensic-tracker
   ```

2. **Create a Python virtual environment:**
   ```bash
   make venv
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -e .[dev,snakemake]
   # Or selectively: pip install -e .[dnaberts,rag,backend] etc.
   ```

4. **Download tool containers and scripts:**
   ```bash
   make download
   ```
   This will pull the required Bioinformatics tool images (as Singularity/Apptainer `.sif` files under `bin/`) and helper scripts (BBMap, DNABERT-S code).

5. **(Optional) Set up Azure credentials** in `.env.azure` for cloud runs, or ensure SLURM configs are correct.

## Configuration

All major settings are in `config/config.yaml`. Key entries:

- `data.raw_dir`: Path to input FASTQ files.
- `data.results_dir`: Root of the output results directory.
- `samples.sample_sheet`: Tab-separated TSV listing `sample`, `r1`, `r2` columns.
- `tools.*`: Paths to tool containers/scripts.
- `databases.*`: Paths to host genome index, Kraken2 database.
- `taxonomy.ranks`: List of taxonomic ranks to process.
- `resources.*`: Resource (threads, memory) specifications for each rule.
- `pipeline.steps.*`: Enable/disable stages (QC, classification, assembly, embeddings, etc).

A separate `config/config_single_run.yaml` is provided for quick testing on a small dataset. Use `config/samples_test.tsv` as a minimal example.

## Usage

### Dry-run / Local

First, always perform a dry-run to check configurations:
```bash
snakemake -n --snakefile workflow/Snakefile
```

For a single-sample test run locally (using a handful of CPUs):
```bash
snakemake \
  --snakefile workflow/Snakefile \
  --profile profiles/single_run \
  --configfile config/config_single_run.yaml
```

### HPC (SLURM)

On an HPC cluster, use the provided SLURM profiles:

```bash
snakemake \
  --snakefile workflow/Snakefile \
  --profile profiles/small_scale \
  --configfile config/config.yaml \
  --config samples_file=config/samples.tsv
```

Or for full production runs:
```bash
snakemake \
  --snakefile workflow/Snakefile \
  --profile profiles/production \
  --configfile config/config.yaml
```
These profiles submit Snakemake jobs as SLURM batch jobs, respecting the resource limits in `config.yaml`.

### Azure Batch (Cloud)

For cloud deployment on Azure:

1. **Build the Azure Batch container image:**  
   ```bash
   docker build -f containers/Dockerfile.batch -t microbiome-batch:latest .
   ```
2. **Push to Azure Container Registry (ACR).**  
3. **Prepare Azure Batch:** Create a Batch pool that mounts the Azure File Share (containing FASTQ and tool images) at `/mnt/data`.
4. **Run Snakemake with Azure Batch profile:**  
   ```bash
   snakemake \
     --snakefile workflow/Snakefile \
     --profile profiles/azure_batch \
     --configfile config/config.yaml
   ```
   The `profiles/azure_batch/config.yaml` is preconfigured for a moderate pool size (4 vCPUs per node). Adjust VM sizes in the profile as needed for heavy jobs (e.g., Kraken2).

### API / Backend Service

A FastAPI application in `src/backend` provides endpoints to upload samples and query results. Current endpoints (under development) include:
- `POST /samples`: Submit a new paired-end FASTQ sample to process.
- `GET /samples`: List previously submitted samples and their status.
- `GET /samples/{id}`: Fetch status and results for a sample.
- `GET /predict?sample_id={id}`: Trigger/retrieve the geolocation prediction for a sample.

By default, the backend uses a local SQLite database. In production, configure it to use an Azure PostgreSQL database. The prediction endpoint loads the trained model from the Azure File Share (`models/` folder) and returns the predicted latitude/longitude (no Celery needed for this quick operation).

## Architecture & Deployment

 *Figure: Conceptual architecture of the Microbiome Forensic Tracker. Raw FASTQ files are uploaded and queued, Snakemake workers run the analysis pipeline, results are written to storage and database, and the FastAPI serves status and predictions.*  

The system is designed to be modular and scalable:

- **Backend:** FastAPI (running in a container on Azure Container Apps or similar) handles HTTP requests. It queues tasks and retrieves results.
- **Task Queue:** Azure Cache for Redis acts as the Celery broker. When a sample is submitted, the FastAPI pushes a Celery task into Redis.
- **Workers:** Celery workers (in containers) listen on Redis. For taxonomic analysis tasks, a worker will trigger Snakemake (via an Azure Batch job or local SLURM submission).
- **Workflow Engine:** Snakemake orchestrates all bioinformatics tools. On Azure, Snakemake uses the Batch profile to run on VM nodes with tools on an Azure File Share (`/mnt/data`).
- **Data Storage:** 
  - **Azure Files** holds input data (`uploads/`), sample configurations (`config/`), and tool images/containers (`bin/`). 
  - **Azure Database for PostgreSQL** (or SQLite) stores metadata, task statuses, and final abundance tables.
- **Machine Learning:** For a given sample, the FastAPI can also directly run the geolocation model. It fetches the required abundance data from the database and loads the pretrained model (from `models/` in Azure Files) into memory. Prediction (latitude/longitude) is returned in the HTTP response.
- **Infrastructure:** Snakemake profiles and helper scripts (`src/smk_helper`) manage resource selection (e.g. choosing proper SLURM partitions or Batch VM sizes).

Together, this architecture ensures reproducibility (via Snakemake), scalability (via HPC/cloud), and a clean separation between analysis (Celery/Snakemake) and serving (FastAPI/API).

## Configuration Details

Important configuration and script files include:

- **`config/samples.tsv`** – Template sample sheet (TSV) listing sample names and FASTQ paths.
- **`config/config.yaml`** – Master config. Customize `data.raw_dir`, `databases.kraken2_db`, etc.
- **`profiles/`** – Execution profiles for different environments: `single_run` (local), `small_scale` & `production` (Slurm), `azure_batch` (Azure).
- **`src/smk_helper/*`** – Helper Python modules for Snakemake:
  - `generate_sample_sheet.py`: auto-generate TSV from a directory of FASTQs.
  - `standardize_bracken.py`: normalize and merge Bracken outputs.
  - `select_partition.py`: logic for selecting SLURM partitions.
  - `dnaberts_embeddings.py`: entrypoint for DNABERT-S embedding step.
- **`containers/`** – Dockerfiles for building the Azure Batch image (`Dockerfile.batch`).
- **`.env.azure`** – Environment variables for Azure authentication (service principal or Managed Identity).

## Testing & Code Quality

Automated tests and linters help ensure reliability:

- Run **pytest** to execute unit tests under `tests/`. Example tests cover the sample-sheet generator, helper scripts, and Bracken standardization.
  ```bash
  pytest tests -v
  ```
- Enforce code style and lint:
  ```bash
  make lint      # runs ruff, black --check, snakefmt
  make format    # applies fixes (ruff --fix, black, snakefmt)
  snakemake --lint  # check Snakefile formatting
  ```
- Continuous Integration (GitHub Actions) is configured to run the above checks on each push. The [CI/CD badge] shows the latest status.

## Upcoming Features / Roadmap

The Microbiome Forensic Tracker is under active development. Planned enhancements include:

- **AI-Generated Forensic Reports:** Integrate an endpoint that uses the Ollama LLM to produce narrative summaries of the forensic analysis results. (e.g. “For this sample, predominant microbes were X, Y, Z; the predicted location is [lat,lon] with confidence…”).
- **Advanced Geolocation Models:** Explore graph-based methods (e.g. taxonomic graph rules in Snakemake, Graph Attention Networks) to improve prediction accuracy by capturing relationships between taxa.
- **Enhanced Sequence Embeddings:** Continue development on DNABERT-S and RAG (retrieval-augmented generation) methods to encode genomic sequences with contextual information.
- **Expanded Backend/API:** Fully wire the FastAPI endpoints to the pipeline (asynchronous task tracking, result retrieval, map visualization, etc.).
- **Additional Datasets:** Incorporate more diverse environmental microbiome datasets to improve model generalizability.

For a detailed roadmap and discussion of new features, see the GitHub Issues and project board.

## Documentation

Comprehensive user guides and reference documentation are available on the project website. The `docs/` directory generates a GitHub Pages site with usage examples, API docs, and tutorials. You can access it here: [Microbiome Forensic Tracker Docs](https://chandrashekarcr.github.io/microbiome-forensic-tracker/).

## Contributing

Contributions are welcome! If you find issues, please file them on GitHub. You can also submit pull requests with bug fixes, new features, or improvements. Please follow the existing code style (see `make format`) and add tests for any new functionality.

## License

This project is licensed under the [MIT License](LICENSE).  
All code, workflows, and documentation are open-source and freely available.  