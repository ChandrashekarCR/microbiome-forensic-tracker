BASE_PYTHON ?= python
PYTHON := .venv/bin/python

DEFAULT_GOAL := all
SHELL := bash
.SHELL_FLAGS := -euo pipefail -c
.PHONY := hello help clean lint venv install
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
