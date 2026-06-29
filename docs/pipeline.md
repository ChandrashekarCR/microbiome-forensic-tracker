# Microbiome Forensic Tracker
## Metagenomic Bioinformatics Workflow Documentation

Version: 1.0  
Author: ChandrashekarCR  

---

# 1. Overview

The **Microbiome Forensic Tracker** is a scalable metagenomic analysis workflow designed for microbial community profiling and DNA sequence representation generation.

The workflow processes raw paired-end sequencing reads and produces:

- quality-controlled sequencing data
- host-filtered microbial reads
- error-corrected reads
- taxonomic abundance profiles
- assembled metagenomic contigs
- DNA language model embeddings

The generated outputs are designed for downstream:

- microbiome comparison
- forensic environmental interpretation
- machine learning based geographic prediction
- microbial signature analysis


The workflow is implemented using:

- **Snakemake** for workflow orchestration
- **SLURM** for HPC scheduling
- **Apptainer containers** for reproducible software execution
- **Conda/Mamba** for environment management


---

# 2. Project Information


| Field | Value |
|-|-|
| Project | malmo_metagenomics_pipeline |
| Version | 1.0 |
| Author | ChandrashekarCR |
| Platform | LUNARC HPC |
| Scheduler | SLURM |

---

# 4. Input Data

## Raw Sequencing Data

The pipeline expects paired-end Illumina reads:

```
sample_R1.fastq.gz
sample_R2.fastq.gz
```

Configuration:

```yaml
samples:

  sample_sheet: config/samples.tsv

  pattern_r1: "_R1.fastq.gz"

  pattern_r2: "_R2.fastq.gz"

  read_length: 150

```

The workflow supports up to:

```
max_samples: 330
```

---

# 5. Software Stack

The pipeline runs all major bioinformatics tools through Apptainer containers.

| Tool            | Purpose                       |
| --------------- | ----------------------------- |
| FastQC          | Sequencing quality assessment |
| fastp           | Read filtering and trimming   |
| Adapter Removal | Adapter cleaning              |
| Bowtie2         | Host genome removal           |
| Samtools        | Alignment processing          |
| BBTools         | Error correction              |
| MEGAHIT         | Metagenomic assembly          |
| Kraken2         | Taxonomic classification      |
| Bracken         | Abundance estimation          |
| MultiQC         | QC aggregation                |

Container examples:

```
bin/fastqc.sif

bin/fastp.sif

bin/kraken2.sif

bin/megahit.sif
```

---

# 6. Processing Steps

# 6.1 Raw Quality Control

Tool:

```
FastQC
```

Purpose:

* evaluate sequencing quality
* detect adapter contamination
* identify poor quality cycles

Output:

```
results/qc/raw/
```

---

# 6.2 Read Cleaning

Tool:

```
fastp
```

Configuration:

```yaml
fastp:

 qualified_quality_phred: 30

 trim_poly_g: true

 dont_eval_duplication: true
```

Operations:

* quality trimming
* poly-G removal
* low-quality filtering

Output:

```
clean_R1.fastq.gz
clean_R2.fastq.gz
```

---

# 6.3 Adapter Removal

Tool:

```
adapter_removal
```

Parameters:

```yaml
trimns: true

trimqualities: true
```

Removes:

* sequencing adapters
* ambiguous bases
* poor quality tails

---

# 6.4 Human DNA Removal

Purpose:

Remove host contamination before microbial analysis.

Tool:

```
Bowtie2
```

Reference:

```
Human hg38 genome
```

Configuration:

```yaml
bowtie2:

 sensitivity: very-sensitive
```

Workflow:

```
Reads

 |

 v

Human genome alignment

 |

 v

Unmapped microbial reads
```

Output:

```
microbial_reads.fastq.gz
```

---

# 6.5 Error Correction

Tool:

BBTools:

* Tadpole
* BBDuk

Purpose:

Improve downstream:

* assembly quality
* classification accuracy

Configuration:

```yaml
memory_gb: 20

k_size: 25

ecc: true

reassemble: true

conservative: true
```

Features:

* k-mer based correction
* sequencing error removal
* conservative correction mode

---

# 7. Taxonomic Profiling Pipeline

# 7.1 Kraken2 Classification

Kraken2 performs k-mer based microbial classification.

Database:

```
core_nt Database
```

Configuration:

```yaml
threads: 12
```

Output:

```
sample.kraken

sample.report
```

---

# 7.2 Bracken Abundance Estimation

Purpose:

Kraken2 assigns reads, while Bracken estimates abundance.

Output:

```
sample.bracken
```

Taxonomic ranks:

```yaml
species
genus
family
order
class
phylum
```

---

# 7.3 Bracken Standardization

Raw Bracken outputs are converted into a consistent format.

Output:

```
standardized_bracken.tsv
```

---

# 7.4 Merge Samples

Multiple samples are combined:

Example:

| Sample | Species A | Species B |
| ------ | --------- | --------- |
| S1     | 0.23      | 0.01      |
| S2     | 0.10      | 0.08      |

Output:

```
merged_taxonomic_profile.tsv
```

This table is used as input for:

* ML models
* classification
* geolocation prediction

---

# 8. Metagenomic Assembly

Tool:

```
MEGAHIT
```

Purpose:

Assemble microbial reads into longer contigs.

Configuration:

```yaml
min_contig_len: 500

k_list:
21,31,41,51,61,71,81,91,101,121,141

min_count: 2
```

Assembly strategy:

* multiple k-mer sizes
* remove rare k-mers
* improve complex metagenome assembly

Output:

```
contigs.fa
```

---

# 9. DNA Sequence Embeddings

Tool:

DNA-BERT-S

Purpose:

Convert DNA sequences into numerical embeddings.

Input:

```
assembled contigs
```

Output:

```
embeddings.npy
```

Configuration:

```yaml
batch_size: 32

max_length: 512

overlap: 0.5

device: cuda
```

These embeddings enable:

* similarity search
* deep learning models
* representation learning

---

# 10. Execution Profiles

The workflow provides multiple execution modes.

---

# 10.1 Single Run Profile

Purpose:

Backend integration.

Used with:

* FastAPI
* Celery
* Redis queue

Architecture:

```
API Request

      |

      v

Celery Worker

      |

      v

Snakemake Job

      |

      v

Results
```

Use case:

Single forensic sample analysis.

---

# 10.2 Small Scale Profile

Purpose:

Development and testing.

Typical workload:

```
5-10 samples
```

Execution:

```bash
snakemake \
--profile profiles/small_scale
```

Optimized for:

* rapid testing
* debugging
* parameter validation

---

# 10.3 Production Profile

Purpose:

Large batch processing.

Target:

```
330 samples
```

Execution:

```bash
snakemake \
--profile profiles/production
```

Optimized for:

* maximum throughput
* parallel SLURM execution
* efficient resource usage

---

# 11. HPC Resource Allocation

Cluster:

```
LUNARC
```

Scheduler:

```
SLURM
```

Partitions:

| Partition | Purpose            |
| --------- | ------------------ |
| lu48      | CPU intensive jobs |
| gpua40    | GPU embedding jobs |
| aurora    | high memory jobs   |

---

# 12. Resource Requirements

Examples:

## Kraken2

High memory task:

```
RAM: 460 GB

CPU: 12
```

Reason:

Core NT database:

```
~310 GB
```

---

## MEGAHIT

```yaml
CPU: 32

Memory: 200 GB
```

Reason:

Large metagenomic assemblies.

---

## DNA-BERT

GPU accelerated:

```yaml
GPU: 1

CPU:12

Memory:32GB
```

---

# 13. Reproducibility

The workflow guarantees reproducibility through:

## Containers

```
Apptainer
```

## Conda

```yaml
use-conda: true
conda-frontend: mamba
```

## Version Controlled Configuration

```
config.yaml

profiles/

workflow/
```

---

# 14. Running the Pipeline

Dry run:

```bash
snakemake -n
```

Production:

```bash
snakemake \
--profile profiles/production
```

Testing:

```bash
snakemake \
--profile profiles/small_scale
```

---

# 15. Outputs

| Stage        | Output                 |
| ------------ | ---------------------- |
| QC           | FastQC reports         |
| Cleaning     | Filtered FASTQ         |
| Host removal | Microbial reads        |
| Correction   | Corrected reads        |
| Kraken2      | Classification reports |
| Bracken      | Abundance tables       |
| Assembly     | Contigs                |
| DNA-BERT     | Embeddings             |

---

# 16. Future Extensions

Planned:

* AI generated forensic reports
* microbiome geolocation prediction
* automated sample interpretation
* cloud deployment
* real-time API processing

---

