import os 
from pathlib import Path
import subprocess

SNAKEFILE = ""
PROFILE = ""
CONFIG_FILE = ""

def run_snakemake_pipeline():
    cmd = ["snakemake",
           "--snakefile" ,str(SNAKEFILE),
           "--profile", str(PROFILE)]