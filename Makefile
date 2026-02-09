BASE_PYTHON ?= python
PYTHON := .venv/bin/python
CONDA_ENV_NAME := binp51_env

DEFAULT_GOAL := all
SHELL := bash
.SHELL_FLAGS := -euo pipefail -c
.PHONY := hello help clean lint venv install conda_env
.SUFFIXES:
.DELETE_ON_ERROR:

# URLS for bioinformatics tools as images
FASTQC_URL := oras://community.wave.seqera.io/library/fastqc:0.12.1--104d26ddd9519960

# Bioninformatics tools as .sif files
TOOL_DIR := bin
FASTQC_IMG := fastqc.sif


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

install: venv
	@echo "Installing packages from requirements.txt file."
	@if [ ! -f requirements.txt ]; then \
		echo "File not found. Ensure you have the requirements file."; \
		exit 1; \
	else \
		. .venv/bin/activate && pip install -r requirements.txt; \
	fi

clean: # Clean all the cache files and .out and .err files from slurm runs
	@find . -type f -name *.err -delete
	@find . -type d -name __pycache__ -exec rm -rf {} + 
	@echo "[clean] ok" 


conda_env: environment.yml
	@if conda env list | grep "$(CONDA_ENV_NAME)"; then \
		echo "Environment already exisits. Syncing packages.."; \
		conda env update -n $(CONDA_ENV_NAME) -f environment.yml --prune;\
	else \
		echo "Environment does not exist. Creating the environment from yml file."; \
		conda env create -f environment.yml; \
	fi
	@echo "Environment is ready. Run conda activate $(CONDA_ENV_NAME) to activate it."
	@echo "[conda_env] ok.."


download: $(FASTQC_IMG)
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


