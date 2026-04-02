BASE_PYTHON ?= python
PYTHON := .venv/bin/python

DEFAULT_GOAL := all
SHELL := bash
.SHELL_FLAGS := -euo pipefail -c
.PHONY := hello help clean lint venv install conda_env
.SUFFIXES:
.DELETE_ON_ERROR:

# URLS for bioinformatics tools as images
FASTQC_URL := oras://community.wave.seqera.io/library/fastqc:0.12.1--104d26ddd9519960
FASTP_URL := oras://community.wave.seqera.io/library/fastp:1.1.0--52619d3aa919a246
ADAPTER_REMOVAL_URL := oras://community.wave.seqera.io/library/adapterremoval:2.3.4--ed2f98d4afa36f48
MULTIQC_URL := oras://community.wave.seqera.io/library/multiqc:1.33--e3576ddf588fa00d
BOWTIE2_URL := oras://community.wave.seqera.io/library/bowtie2:2.5.4--2ec535d45cd82f0b
SAMTOOLS_URL := oras://community.wave.seqera.io/library/samtools:1.23--86cd9d13645d4fff
TADPOLE_URL := https://sourceforge.net/projects/bbmap/files/BBMap_39.70.tar.gz
SPADES_URL := oras://community.wave.seqera.io/library/spades:4.2.0--3313822b80929818
KRAKEN2_URL := oras://community.wave.seqera.io/library/kraken2:2.17.1--1738c34504f3fb18
BRACKEN_URL := oras://community.wave.seqera.io/library/bracken:3.1--77382b4340548c89
PANDASEQ_URL := docker://dromero93/pandaseq:latest
MEGAHIT_URL := oras://community.wave.seqera.io/library/megahit:1.2.9--8488ea3ad736bcd8

# Bioninformatics tools as .sif files
TOOL_DIR := bin
FASTQC_IMG := fastqc.sif
FASTP_IMG := fastp.sif
ADAPTER_REMOVAL_IMG := adapter_removal.sif
MULTIQC_IMG := multiqc.sif
BOWTIE2_IMG := bowtie2.sif
SAMTOOLS_IMG := samtools.sif 
TADPOLE_TOOL := "$(TOOL_DIR)/bbmap/tadpole.sh"
SPADES_TOOL := spades.sif
KRAKEN2_TOOL := kraken2.sif
BRACKEN_TOOL := bracken.sif
PANDASEQ_TOOL := pandaseq.sif
MEGAHIT_TOOL := megahit.sif

hello: # Hello Makefile
	@echo "Makefile working.."
	@echo "[hello] ok.."


venv: # Create virtual environement
	@if [ ! -d .venv ]; then \
		echo "Environment not found. Creating environement with $(BASE_PYTHON)."; \
		$(BASE_PYTHON) -m venv .venv; \
	fi

	@. .venv/bin/activate && pip install -U pip
	@echo "[venv] ready .."

install: venv # Install packages from requirements.txt file.
	@echo "Installing packages from requirements.txt file."
	@if [ ! -f requirements.txt ]; then \
		echo "File not found. Ensure you have the requirements file."; \
		exit 1; \
	else \
		. .venv/bin/activate && pip install -r requirements.txt; \
	fi
	@echo "[install] ok"

clean: # Clean all the cache files and .out and .err files from slurm runs
	@find . -type f -name "*.err" -delete
	@find . -type f -name "*.out" -delete
	@find . -type d -name "__pycache__" -exec rm -rf {} +
	@find . -type d -name "*.egg-info" -exec rm -rf {} +
	@find . -type d -name ".pytest_cache" -exec rm -rf {} +
	@find . -type d -name ".ruff_cache" -exec rm -rf {} +
	@echo "[clean] ok"

lint: # Linting python scripts
	@$(PYTHON) -m ruff check . || (echo '[lint] ruff failed' >&2; exit 1)
	@echo "[lint] ok"

format: # Code formatting using ruff and black
	@echo "Organizing imports with ruff.."
	@$(PYTHON) -m ruff check --fix src/ tests/ || (echo '[format] ruff import sorting failed' >&2; exit 1)
	@echo "Formatting code with black"
	@$(PYTHON) -m black src/ tests/ || (echo '[format] black formatting failed' >&2; exit 1)
	@echo "Formatting snakemake rules and files with snakefmt.."
	@. .venv-snakemake/bin/activate && snakefmt workflow/rules/*.smk workflow/Snakefile || (echo '[format] snakefmt formatting failed' >&2; exit 1)
	@echo "[format] ok."	

test: # Run pytests for script
	@echo "Running core tests.."
	@echo "[test] ok"

venv-snakemake: # For snakemake excecution
	@echo "Installing Snakemake and dev tools for development"
	@$(PYTHON) -m venv .venv-snakemake
	@. .venv-snakemake/bin/activate && pip install -U pip && pip install -e ".[snakemake,dev]"
	@echo "[venv-snakemake] ok"

venv-dnaberts: # For DNABERT-S development
	@echo "Installing DNABERT-S and dev tools for development."
	@$(PYTHON) -m venv .venv-dnaberts
	@. .venv-dnaberts/bin/activate && pip install -U pip && pip install -e ".[dnaberts,dev]"
	@echo "[venv-dnaberts] ok"

venv-rag: # For RAG development
	@echo "Installating RAG and dev tools environment for development."
	@$(PYTHON) -m venv .venv-rag
	@. .venv-rag/bin/activate && pip install -U pip && pip install -e ".[rag,dev]"
	@echo "[venv-rag] ok"

venv-backend: # For backend development
	@echo "Installing backend and dev tools environment for development."
	@$(PYTHON) -m venv .venv-backend
	@. .venv-backend/bin/activate && pip install -U pip && pip install -e ".[backend,dev]"
	@echo "[venv-backend] ok"

download: $(FASTQC_IMG) $(FASTP_IMG) $(ADAPTER_REMOVAL_IMG) $(MULTIQC_IMG) $(BOWTIE2_IMG) \
		 $(SAMTOOLS_IMG) $(TADPOLE_TOOL) $(SPADES_TOOL) $(KRAKEN2_TOOL) $(BRACKEN_TOOL) \
		 $(PANDASEQ_TOOL) $(MEGAHIT_TOOL)

	@if [ ! -d $(TOOL_DIR) ]; then \
		echo "Directory for downloading images does not exist. Creating...";\
		mkdir -p "$(TOOL_DIR)";\
	else \
		echo "Directory already exists...";\
	fi
	@echo "[download] ok"

$(FASTQC_IMG):
	@if [ ! -f "$(TOOL_DIR)/$@" ]; then \
		echo "Dowloading fastqc tool.";\
		apptainer pull "$(TOOL_DIR)/$@" "$(FASTQC_URL)";\
	else \
		echo "Fastqc already exists.";\
	fi

$(FASTP_IMG):
	@if [ ! -f "$(TOOL_DIR)/$@" ]; then \
		echo "Dowloading fastp tool.";\
		apptainer pull "$(TOOL_DIR)/$@" "$(FASTP_URL)";\
	else \
		echo "FastP already exists.";\
	fi

$(ADAPTER_REMOVAL_IMG):
	@if [ ! -f "$(TOOL_DIR)/$@" ]; then \
		echo "Dowloading adapter removal tool." ;\
		apptainer pull "$(TOOL_DIR)/$@" "$(ADAPTER_REMOVAL_URL)" ;\
	else \
		echo "Adapter removal already exists." ;\
	fi

$(MULTIQC_IMG):
	@if [ ! -f "$(TOOL_DIR)/$@" ]; then \
		echo "Dowloading multiqc tool.";\
		apptainer pull "$(TOOL_DIR)/$@" "$(MULTIQC_URL)" ;\
	else \
		echo "Multiqc image alread exists";\
	fi
$(BOWTIE2_IMG):
	@if [ ! -f "$(TOOL_DIR)/$@" ]; then \
		echo "Downloading bowtie2 tool.";\
		apptainer pull "$(TOOL_DIR)/$@" "$(BOWTIE2_URL)" ;\
	else \
		echo "Bowtie2 already exists.";\
	fi

$(SAMTOOLS_IMG):
	@if [ ! -f "$(TOOL_DIR)/$@" ]; then \
		echo "Downloading samtools tool.";\
		apptainer pull "$(TOOL_DIR)/$@" "$(SAMTOOLS_URL)" ;\
	else \
		echo "Samtools already exists.";\
	fi

$(TADPOLE_TOOL):
	@if [ ! -f $(TOOL_DIR)/bbmap/tadpole.sh ]; then \
		echo "Downloading tadpole tools.";\
		mkdir -p $(TOOL_DIR)/bbmap;\
		wget -O $(TOOL_DIR)/bbmap.tar.gz "$(TADPOLE_URL)";\
		tar -xvzf $(TOOL_DIR)/bbmap.tar.gz -C $(TOOL_DIR)/bbmap --strip-components=1;\
	else \
		echo "Tadpole already exists.";\
	fi

$(SPADES_TOOL):
	@if [ ! -f "$(TOOL_DIR)/$@" ]; then \
		echo "Downloading spades tool.";\
		apptainer pull "$(TOOL_DIR)/$@" "$(SPADES_URL)" ;\
	else \
		echo "Spades already exists.";\
	fi

$(KRAKEN2_TOOL):
	@if [ ! -f "$(TOOL_DIR)/$@" ]; then \
		echo "Downloading kraken2 tool.";\
		apptainer pull "$(TOOL_DIR)/$@" "$(KRAKEN2_URL)" ;\
	else \
		echo "Kraken2 already exists.";\
	fi

$(BRACKEN_TOOL):
	@if [ ! -f "$(TOOL_DIR)/$@" ]; then \
		echo "Downloading bracken tool.";\
		apptainer pull "$(TOOL_DIR)/$@" "$(BRACKEN_URL)" ;\
	else \
		echo "Bracken already exists.";\
	fi

$(PANDASEQ_TOOL):
	@if [ ! -f "$(TOOL_DIR)/$@" ]; then \
		echo "Downloading pandaseq tool.";\
		apptainer pull "$(TOOL_DIR)/$@" "$(PANDASEQ_URL)" ;\
	else \
		echo "Pandaseq already exists.";\
	fi

$(MEGAHIT_TOOL):
	@if [ ! -f "$(TOOL_DIR)/$@" ]; then \
		echo "Downloading megahit tool.";\
		apptainer pull "$(TOOL_DIR)/$@" "$(MEGAHIT_URL)" ;\
	else \
		echo "Megahit already exists.";\
	fi