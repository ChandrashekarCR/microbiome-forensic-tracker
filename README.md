# BINP51 — Metagenomics Pipeline

[![CI/CD pipeline](https://github.com/ChandrashekarCR/microbiome-forensic-tracker/workflows/CI%2FCD%20pipeline/badge.svg)](https://github.com/ChandrashekarCR/microbiome-forensic-tracker/actions/workflows/ci.yaml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black) 
[![Snakemake](https://img.shields.io/badge/snakemake-≥7-brightgreen.svg)](https://snakemake.readthedocs.io)
[![GitHub issues](https://img.shields.io/github/issues/ChandrashekarCR/microbiome-forensic-tracker)](https://github.com/ChandrashekarCR/microbiome-forensic-tracker/issues)
[![GitHub last commit](https://img.shields.io/github/last-commit/ChandrashekarCR/microbiome-forensic-tracker)](https://github.com/ChandrashekarCR/microbiome-forensic-tracker/commits)

BINP51 is an end-to-end metagenomics workflow for paired-end FASTQ data. It performs:

- read-level QC and preprocessing,
- host-read removal,
- taxonomic profiling with Kraken2 + Bracken,
- report standardization/merging,
- assembly with MEGAHIT,
- contig embeddings with DNABERT-S.

The workflow is implemented in Snakemake and designed for HPC usage (LUNARC SLURM profiles are included).

---

## 1) Repository overview

Top-level structure (simplified):

```text
binp51/
├── workflow/
│   ├── Snakefile
│   └── rules/
│       ├── qc.smk
│       ├── preprocessing.smk
│       ├── classification.smk
│       ├── postprocessing.smk
│       ├── assembly.smk
│       ├── bert.smk
│       └── common.smk
├── config/
│   ├── config.yaml
│   ├── config_single_run.yaml
│   ├── samples.tsv
│   └── samples_test.tsv
├── src/
│   ├── smk_helper/
│   ├── backend/
│   ├── malmo_samples/
│   ├── mixed_samples/
│   └── rag/
├── tests/
├── profiles/
│   ├── single_run/
│   ├── small_scale/
│   └── production/
├── scripts/
├── Makefile
└── pyproject.toml
```

---

## 2) Pipeline stages

The default pipeline graph in `workflow/Snakefile` includes:

1. `fastqc_raw` — FastQC on raw reads
2. `fastp` — quality filtering/trimming
3. `adapter_removal` — AdapterRemoval
4. `remove_human_reads` — host depletion with Bowtie2
5. `error_correction` — BBMap tools (`repair.sh`, `tadpole.sh`, fallback `bbduk.sh`)
6. `fastqc_processed` — FastQC on corrected reads
7. `multiqc` — aggregated QC report
8. `kraken` — taxonomic classification
9. `bracken` — abundance estimation per rank
10. `standardize_bracken` — normalize Bracken output format
11. `merge_bracken` — merge all samples by rank
12. `megahit_assembly` — assembly
13. `dnaberts_embeddings` — DNABERT-S embeddings from contigs

Outputs are organized under the configured `results_dir` with numbered stage folders.

---

## 3) Requirements

### Runtime

- Linux
- Python >= 3.9
- Apptainer (for `.sif` tool images)
- SLURM (for cluster execution profiles)

### Python dependencies

Managed in `pyproject.toml` with optional groups:

- `dev`
- `snakemake`
- `dnaberts`
- `rag`
- `backend`

---

## 4) Environment setup

You can use the provided Make targets.

### Base dev environment

```bash
make venv
```

### Specialized environments

```bash
make venv-snakemake
make venv-dnaberts
make venv-rag
make venv-backend
```

### Install containers/tools

```bash
make download
```

This pulls tool images to `bin/` (FastQC, fastp, AdapterRemoval, Bowtie2, Samtools, SPAdes, Kraken2, Bracken, MEGAHIT, etc.) and unpacks BBMap helper scripts.

---

## 5) Configuration

Primary config file: `config/config.yaml`

Important keys:

- `data.raw_dir` — source FASTQ directory
- `data.results_dir` — output root
- `samples.sample_sheet` — TSV with columns `sample`, `r1`, `r2`
- `tools.*` — container/script locations
- `databases.*` — host genome and Kraken2 DB paths
- `taxonomy.ranks` — output ranks (`species`, `genus`, `family`, `order`, `class`, `phylum`)
- `resources.*` — per-rule memory/runtime/thread settings
- `pipeline.steps.*` — stage on/off switches

For single-run testing, see `config/config_single_run.yaml`.

---

## 6) Running the workflow

### A) Local dry-run (recommended first)

```bash
snakemake --snakefile workflow/Snakefile -n
```

### B) Single run profile

```bash
snakemake \
	--snakefile workflow/Snakefile \
	--profile profiles/single_run \
	--configfile config/config_single_run.yaml
```

### C) Small-scale profile (HPC)

```bash
snakemake \
	--snakefile workflow/Snakefile \
	--profile profiles/small_scale \
	--configfile config/config_single_run.yaml \
	--config samples_file=config/samples_test.tsv
```

### D) Production profile (HPC)

```bash
snakemake \
	--snakefile workflow/Snakefile \
	--profile profiles/production \
	--configfile config/config.yaml
```

---

## 7) Utility scripts and helper modules

### Snakemake helpers (`src/smk_helper`)

- `generate_sample_sheet.py` — generate sample TSV from FASTQ directory
- `helper_scripts.py` — load/validate sample sheet and accessor helpers
- `standardize_bracken.py` — Bracken normalization + merge utilities
- `select_partition.py` — cluster partition chooser for heavy jobs
- `dnaberts_embeddings.py` — DNABERT-S embedding entrypoint

### Example: generate sample sheet

```bash
python src/smk_helper/generate_sample_sheet.py \
	-i /path/to/fastq_dir \
	-o config/samples.tsv
```

---

## 8) Testing and code quality

### Current tests

- `tests/test_generate_sample_sheet.py`
- `tests/test_helper_scripts.py`
- `tests/test_standardize_bracken.py`

### Run tests

```bash
pytest tests -v
```

### Lint/format

```bash
make lint
make format
```

Notes:

- `make format` runs `ruff --fix`, `black`, and `snakefmt`.
- Ensure `.venv` (and `.venv-snakemake` for `snakefmt`) exists before running formatting targets.

---

## 9) Backend/API (work in progress)

The `src/backend` module contains an evolving FastAPI service for sample uploads and result tracking (`sqlite` backend).

Main endpoints currently include:

- `GET /` health/status
- `POST /samples` upload paired FASTQ
- `GET /samples` list submitted samples
- `GET /map` serve interactive map HTML

This API layer is under active development and not yet fully wired to robust asynchronous pipeline execution.

---

## 10) CI/CD recommendations

Before publishing, run locally:

```bash
make format
make lint
pytest tests -v
snakemake --snakefile workflow/Snakefile --lint
```

Then add GitHub Actions with stages:

1. install (`pip install -e .[dev,snakemake]`)
2. lint (`ruff`, `black --check`)
3. tests (`pytest`)
4. optional Snakemake lint/dry-run

---

## 11) Known constraints

- Some default config values point to local/HPC-specific absolute paths.
- DNABERT-S embedding is GPU-oriented; CPU fallback exists but is slower.
- Large Kraken2 DB (core-nt) workloads require high-memory partitions.

---

## 12) License

This project is licensed under the MIT License. See `LICENSE`.

