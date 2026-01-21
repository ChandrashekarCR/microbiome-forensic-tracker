# These are some of the common functions that the metagenomics pipeline uses

# Import libraries
import os
import glob
from pathlib import Path

def get_samples(samples_dir, read1_suffix):
    """
    Get the list of samples from the FASTQ Directory
    
    :param samples_dir: Path to the directory containing the fastq files
    :param read1_suffix: Suffix for R1 files (something like "_R1.fastq.gz")
    """

    # Reads all the 
    pattern = os.path.join(samples_dir, f"*{read1_suffix}")
    print(glob.glob(pattern))



get_samples("/lunarc/nobackup/projects/snic2019-34-3/shared_elhaik_lab1/Projects/Microbiome/Mixed2025/fastq_files",
            '_R1.fastq.gz')

    


