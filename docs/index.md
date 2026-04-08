# Microbiome Forensic Tracker — Documentation

## Overview

**Microbiome Forensic Tracker** is a forensic metagenomics platform that predicts the geographical origin of environmental samples based on their microbial composition. 

The core insight: microbiomes are spatially distinct. Soil, water, and surface samples from different locations harbor unique microbial signatures. By profiling these signatures and learning location-specific patterns, we can reverse-engineer where an unknown sample originated—enabling forensic applications in environmental investigation.

---

## Who Is This For?

- **Forensic investigators** — determine sample origin in environmental crime scenes
- **Environmental microbiologists** — study microbial biogeography and spatial ecology
- **Bioinformaticians** — process metagenomic FASTQ data at scale on HPC clusters
- **Researchers** — leverage machine learning + RAG for microbiome interpretation

---

## What Does It Do?

### 1. **Bioinformatic Processing Pipeline**
A modular Snakemake workflow transforms raw paired-end FASTQ data into actionable microbiome profiles:

- **Quality Control** — FastQC, read filtering (fastp), adapter removal
- **Host Depletion** — remove human/background reads via Bowtie2
- **Error Correction** — BBMap repair and tadpole tools
- **Taxonomic Profiling** — Kraken2 classification + Bracken abundance estimation
- **Assembly** — MEGAHIT contig assembly
- **Embeddings** — DNABERT-S DNA language model representations

All outputs are standardized, merged, and organized by processing stage.

### 2. **Machine Learning for Geolocation Prediction**
Once processed, microbiome profiles are fed into ML models (UMAP, clustering, classifiers) to:

- Identify zone-specific microbial markers
- Project samples into latent space for visualization
- Train location predictors
- Validate clustering quality and feature importance

### 3. **RAG-Based Interpretation**
An Ollama-powered Retrieval-Augmented Generation (RAG) system:

- Profiles environments based on detected species and metabolic functions
- Provides interpretable summaries of microbial communities
- Connects taxonomic findings to ecological context
- Enables natural language queries about sample provenance

### 4. **Web Backend & Interactive Mapping**
A FastAPI service provides:

- Sample upload and pipeline submission
- SQLite-backed metadata tracking
- Interactive Folium maps with sample locations, zones, and clustering
- RESTful endpoints for downstream analysis

---

## Quick Workflow

```
Raw FASTQ Files
       ↓
  [Snakemake Pipeline]
  ├─ QC (FastQC, fastp)
  ├─ Host removal (Bowtie2)
  ├─ Error correction (BBMap)
  ├─ Taxonomy (Kraken2 + Bracken)
  ├─ Assembly (MEGAHIT)
  └─ Embeddings (DNABERT-S)
       ↓
  Standardized Microbiome Profiles
       ↓
  [ML Analysis]
  ├─ UMAP visualization
  ├─ Zone-based clustering
  └─ Feature extraction
       ↓
  [RAG Interpretation]
  ├─ Species profiling
  ├─ Environment characterization
  └─ Geolocation prediction
       ↓
  Interactive Web Interface
  ├─ Map visualization
  ├─ Sample metadata
  └─ Prediction results
```

---

## Key Features

**Production-Ready HPC Integration** — SLURM profiles for LUNARC, dynamic resource allocation  
**Containerized Tools** — Apptainer images ensure reproducibility  
**Modular Architecture** — Enable/disable pipeline stages via config  
**Spatial Analytics** — Zone assignment, geographical clustering, location inference  
**Interpretability** — RAG + natural language explanations of microbiome findings  
**Web-Ready Backend** — FastAPI + SQLite for sample tracking and API access  
**Comprehensive Testing** — Unit tests for helpers, Snakemake linting, CI/CD ready  

---

## Technology Stack

| Layer | Tools |
|-------|-------|
| **Workflow** | Snakemake ≥7, SLURM |
| **Bioinformatics** | Kraken2, Bracken, MEGAHIT, BBMap, Bowtie2, FastQC, fastp |
| **ML/Embeddings** | DNABERT-S, UMAP, scikit-learn |
| **RAG** | Ollama, LangChain, embedding models |
| **Backend** | FastAPI, SQLite, Celery (optional async) |
| **Frontend** | Folium (interactive maps), HTML5 |
| **Environment** | Python 3.9+, Apptainer, Linux |

---

## Getting Started

### 1. Clone & Setup
```bash
git clone https://github.com/ChandrashekarCR/microbiome-forensic-tracker.git
cd microbiome-forensic-tracker
make venv
make download  # Pull tool containers and databases
```

### 2. Configure
Edit `config/config.yaml` with your:
- FASTQ directory paths
- Sample metadata (sample sheet TSV)
- Kraken2 database location
- Output directories

### 3. Run (HPC)
```bash
snakemake \
  --snakefile workflow/Snakefile \
  --profile profiles/production \
  --configfile config/config.yaml
```

### 4. Analyze & Visualize
```bash
python src/ml/data_loading.py -i databases/malmo.db
python src/ml/utils.py --plot-umap  # UMAP by zone
python src/malmo_samples/interactive_malmo_city_plot.py  # Interactive map
```

### 5. Query with RAG
```bash
# (Coming soon: web interface)
# For now: integrate Ollama RAG pipeline manually
python src/rag/05_forensic_pipeline/predict_location.py
```

---

## Project Structure

```
microbiome-forensic-tracker/
├── workflow/              # Snakemake pipeline
│   ├── Snakefile
│   └── rules/
│       ├── qc.smk
│       ├── preprocessing.smk
│       ├── classification.smk
│       ├── assembly.smk
│       ├── bert.smk
│       └── common.smk
├── src/
│   ├── smk_helper/        # Snakemake utility functions
│   ├── malmo_samples/     # Spatial mapping & metadata
│   ├── ml/                # ML models & UMAP analysis
│   ├── rag/               # RAG pipeline & forensic queries
│   └── backend/           # FastAPI service
├── config/                # Configuration files
├── profiles/              # HPC execution profiles
├── tests/                 # Unit tests
├── docs/                  # Documentation
└── Makefile              # Development targets
```

---

## Documentation

- **[README.md](../README.md)** — Technical setup, CLI reference, pipeline stages
- **[Installation](installation.md)** — Detailed environment & dependency setup
- **[Configuration](configuration.md)** — Config file reference & customization
- **[Pipeline Guide](pipeline.md)** — Workflow stages & outputs
- **[ML & Analysis](ml_analysis.md)** — UMAP, clustering, geolocation models
- **[RAG Module](rag.md)** — Using Ollama for interpretation
- **[Backend API](backend.md)** — FastAPI endpoints & data model
- **[FAQ](faq.md)** — Common issues & troubleshooting

---

## Use Cases

### Forensic Investigation
- Recover soil sample from crime scene
- Process microbiome profile
- Predict geographical origin
- Cross-reference with known zone signatures
- Generate interpretable report

### Environmental Sampling
- Compare microbiomes across water bodies, parks, beaches
- Identify location-specific species markers
- Study microbial biogeography
- Build predictive models for unknown samples

### Research & Education
- Teach bioinformatics pipelines on real data
- Explore HPC workflows with Snakemake
- Learn embeddings & ML on biological sequences
- Experiment with RAG for scientific interpretation

---

## Citation

If you use this platform in research, please cite:

```bibtex
@software{microbiome_forensic_tracker,
  author = {Chandrashekar, CR},
  title = {Microbiome Forensic Tracker: Geolocation Prediction from Microbial Signatures},
  year = {2026},
  url = {https://github.com/ChandrashekarCR/microbiome-forensic-tracker}
}
```

---

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Run tests & linting (`make format`, `make lint`, `pytest`)
4. Submit a pull request

See [CONTRIBUTING.md](../CONTRIBUTING.md) for details.

---

## License

Licensed under the MIT License. See [LICENSE](../LICENSE).

---

## Support

- **Issues** — [GitHub Issues](https://github.com/ChandrashekarCR/microbiome-forensic-tracker/issues)
- **Discussions** — [GitHub Discussions](https://github.com/ChandrashekarCR/microbiome-forensic-tracker/discussions)
- **Email** — chandrashekar@example.com

---

**Last updated**: April 2026