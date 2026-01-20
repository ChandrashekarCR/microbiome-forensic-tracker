BASE_PYTHON ?= python
PYTHON := .venv/bin/python
CONDA_ENV_NAME := binp51_env

DEFAULT_GOAL := all
SHELL := bash
.SHELL_FLAGS := -euo pipefail -c
.PHONY := hello help clean lint venv install conda_env
.SUFFIXES:
.DELETE_ON_ERROR:


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