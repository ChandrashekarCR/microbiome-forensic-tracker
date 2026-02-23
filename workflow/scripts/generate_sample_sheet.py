import argparse
import os
import sys
from pathlib import Path

def generate_sample_sheet(data_dir: str, output: str = None):
    data_path = Path(data_dir)

    if not data_path.exists():
        print(f"ERROR: data-dir dos not exists: {data_dir}",file=sys.stderr)
        sys.exit(1)
    
    # Find all the R1 files
    r1_files = sorted(data_path.glob("*_R1.fastq.gz"))
    
    rows = []

    for r1 in r1_files:
        # Derive the sample name
        sample = r1.name.replace("_R1.fastq.gz","")
        r2 = Path(str(r1).replace("_R1","_R2"))

        rows.append((sample,r1,r2))
    
    # Write TSV
    output_path = Path(output)
    output_path.parent.mkdir(parents=True,exist_ok=True)

    with open(output_path,"w") as fo:
        fo.write("sample\tr1\tr2\n")
        for sample,r1,r2 in rows:
            fo.write(f"{sample}\t{r1}\t{r2}\n")

    print(f"Written {len(rows)} samples to {output}", file=sys.stderr)


generate_sample_sheet(
    data_dir="/lunarc/nobackup/projects/snic2019-34-3/shared_elhaik_lab1/Projects/Microbiome/Malmo2025/fastq_files",
    output="/home/chandru/binp51/config/samples.tsv"
)