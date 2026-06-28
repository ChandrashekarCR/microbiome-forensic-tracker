# Microbiome Forensic Tracker
## Bioinformatics Workflow Documentation

## Overview

The **Microbiome Forensic Tracker** workflow is a modular metagenomic analysis pipeline designed to process raw sequencing reads and generate microbial profiles and sequence-based representations for downstream forensic and geolocation analysis.

The pipeline is implemented using **Snakemake**, enabling:

- reproducible execution
- modular rule-based processing
- scalable execution on HPC clusters
- isolated software environments
- automatic dependency management

The workflow processes raw sequencing data through quality control, preprocessing, host removal, taxonomic profiling, and sequence embedding generation.

---

# Workflow Architecture

The pipeline consists of three major analysis branches:

1. **Taxonomic Profiling Branch**
   - Identifies microbial organisms present in a sample
   - Generates abundance tables suitable for machine learning

2. **Sequence Embedding Branch**
   - Converts assembled DNA sequences into numerical representations
   - Enables deep-learning based downstream analysis


---

# Directory Structure

The workflow follows a modular Snakemake structure.

Example:

```
workflow/
├── rules
│   ├── assembly.smk
│   ├── bert.smk
│   ├── classification.smk
│   ├── common.smk
│   ├── postprocessing.smk
│   ├── preprocessing.smk
│   └── qc.smk
└── Snakefile

src/smk_helper/
├── dnaberts_embeddings.py
├── generate_sample_sheet.py
├── helper_scripts.py
├── __init__.py
├── resource_usage.py
├── select_partition.py
└── standardize_bracken.py
```

---

# Pipeline Stages

## 1. Raw Sequencing Input

### Input

The workflow accepts paired-end metagenomic sequencing reads:

```
sample_R1.fastq.gz
sample_R2.fastq.gz
```

These represent the raw sequencing output generated from a sequencing platform.

---

# 2. Quality Control

## Purpose

The quality control stage evaluates sequencing quality before downstream processing.

Typical metrics:

* per-base sequence quality
* GC distribution
* adapter contamination
* read length distribution

## Tools

| Tool               | Purpose                    |
| ------------------ | -------------------------- |
| FastQC             | Initial quality assessment |
| MultiQC (optional) | Aggregated QC reporting    |

Output:

```
results/qc/
    sample_fastqc.html
    sample_fastqc.zip
```

---

# 3. Read Trimming and Filtering

## Purpose

Remove:

* sequencing adapters
* low-quality bases
* short reads
* unreliable sequences


Output:

```
clean_reads/

sample_R1.clean.fastq.gz
sample_R2.clean.fastq.gz
```

---

# 4. Host DNA Removal

## Purpose

Environmental and forensic samples may contain host DNA.

The workflow removes unwanted host-derived reads before microbial analysis.

Example:

```
Human reference genome
          |
          v
Alignment/filtering
          |
          v
Microbial reads retained
```

Output:

```
microbial_reads.fastq.gz
```

---

# 5. Error Correction

## Purpose

Correct sequencing errors before classification and assembly.

Benefits:

* improves taxonomic assignment
* improves assembly quality
* reduces false classifications

Output:

```
corrected_reads.fastq.gz
```

---

# Taxonomic Profiling Workflow

## 6. Kraken2 Classification

## Purpose

Kraken2 performs k-mer based taxonomic classification.

Input:

```
corrected_reads.fastq.gz
```

Output:

```
sample.kraken
sample.report
```

Generated information:

* classified reads
* taxonomic assignments
* confidence scores

Example configuration:

```yaml
kraken2:

 database: /path/to/database

 confidence: 0.1

 threads: 16
```

---

# 7. Bracken Abundance Estimation

## Purpose

Kraken2 assigns reads but abundance estimation can be improved using Bracken.

Bracken re-estimates species abundance by redistributing reads among taxonomic nodes.

Input:

```
sample.kraken
```

Output:

```
sample.bracken
```

Example:

```yaml
bracken:

 read_length: 150

 threshold: 10
```

---

# 8. Taxonomic Table Generation

The workflow converts individual Bracken outputs into machine-learning compatible matrices.

Example:

| Sample | Species A | Species B | Species C |
| ------ | --------- | --------- | --------- |
| S1     | 0.20      | 0.05      | 0.01      |
| S2     | 0.15      | 0.10      | 0.02      |

Output:

```
merged_abundance_table.tsv
```

This table is used for:

* microbiome comparison
* classification
* geolocation prediction
* forensic interpretation

---

# Sequence Embedding Workflow

## 9. Metagenomic Assembly

## Purpose

Reads are assembled into longer DNA sequences (contigs).

Input:

```
corrected_reads.fastq.gz
```

Output:

```
contigs.fasta
```

Assembly improves:

* sequence context
* feature extraction
* downstream representation learning

---

# 10. DNA Sequence Embeddings

## Purpose

DNA sequences are converted into numerical vectors using DNA language models.

Example:

```
DNA sequence

ATGCGTAGCT...

        |

        v

Embedding model

        |

        v

[0.23, -0.11, 0.54, ...]
```

Output:

```
embeddings.npy
```

These embeddings can be used for:

* machine learning models
* clustering
* similarity search
* geographic prediction

---

# Configuration

The workflow uses YAML configuration files.

## config.yaml

Controls:

* input files
* database locations
* parameters
* resources

Example:

```yaml
samples:
  - sample1
  - sample2


kraken_database:

 /data/kraken_db


threads:

 16
```

---

# HPC Execution

The workflow supports SLURM clusters.

Example:

```yaml
__default__:

 partition: compute

 time: "08:00:00"

 mem: 32G

 cpus: 4


kraken2:

 mem: 128G

 cpus: 16
```

---

# Running the Workflow

## Local execution

```bash
snakemake \
--snakefile workflow/Snakefile \
--configfile config/config.yaml
```

## Dry Run

Before execution:

```bash
snakemake -n
```

## HPC Execution

```bash
snakemake \
--profile slurm \
-j 100
```

---

# Output Summary

| Component     | Output                |
| ------------- | --------------------- |
| QC            | FastQC reports        |
| Preprocessing | Clean FASTQ files     |
| Host removal  | Microbial reads       |
| Kraken2       | Taxonomic assignments |
| Bracken       | Abundance estimates   |
| Assembly      | Contigs               |
| Embeddings    | DNA vectors           |

---

# Reproducibility

The workflow uses:

* Snakemake rules
* Conda environments
* Version-controlled configuration
* Explicit input/output tracking

Each rule runs in an isolated environment:

Example:

```
workflow/envs/

fastqc.yaml

fastp.yaml

kraken.yaml

bracken.yaml
```

---

# Extending the Pipeline

New tools can be added by:

1. Creating a new Snakemake rule

2. Adding a Conda environment

3. Updating configuration

4. Connecting outputs to downstream rules

Example:

```
new_tool_rule

        |

        v

new_output.tsv

        |

        v

machine_learning_stage
```

---

# Troubleshooting

## Memory Error

Increase resources:

```yaml
mem: 128G
```

---

## Missing Database

Check:

```yaml
kraken_database:
    /correct/path
```

---

## Environment Failure

Recreate:

```bash
conda env create \
-f workflow/envs/tool.yaml
```

---

# Future Development

Planned extensions:

* automated forensic report generation
* geographic prediction models
* neural embedding models
* interactive visualization dashboard
* cloud execution support

---

# References

Snakemake:
[https://snakemake.readthedocs.io/](https://snakemake.readthedocs.io/)

Kraken2:
[https://github.com/DerrickWood/kraken2](https://github.com/DerrickWood/kraken2)

Bracken:
[https://github.com/jenniferlu717/Bracken](https://github.com/jenniferlu717/Bracken)

Fastp:
[https://github.com/OpenGene/fastp](https://github.com/OpenGene/fastp)

FastQC:
[https://www.bioinformatics.babraham.ac.uk/projects/fastqc/](https://www.bioinformatics.babraham.ac.uk/projects/fastqc/)

```

I would **not** claim exact filenames like `qc.smk`, `kraken.smk`, etc. in the final repository unless those files actually exist; replace those placeholders after checking your `workflow/` directory. The structure above matches how production Snakemake metagenomics workflows are typically organized. :contentReference[oaicite:1]{index=1}
```

[1]: https://pmc.ncbi.nlm.nih.gov/articles/PMC10591440/?utm_source=chatgpt.com "aMeta: an accurate and memory-efficient ancient metagenomic profiling workflow - PMC"
