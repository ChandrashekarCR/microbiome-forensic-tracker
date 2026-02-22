import argparse
import os
import sys
from pathlib import Path

def generate_sample_sheet(data_dir: str, output: str):
    data_path = Path(data_dir)

    if not data_path.exists():
        print(f"ERROR: data-dir dos not exists: {data_dir}",file=sys.stderr)
        sys.exit(1)
    
    # Find all the R1 files
    r1_files = sorted(data_path.glob("*_R1.fastq.gz"))
    print(r1_files)

