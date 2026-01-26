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
    files = glob.glob(pattern)

    if not files:
        raise ValueError(
            f"No files found matching the patter: {pattern}\n"
            f"Check you samples_dir and read1_suffix in the config.yaml file."
        )   

    samples = []
    for f in files:
        sample_name = os.path.basename(f).replace(read1_suffix,"")
        samples.append(sample_name)
    
    return sorted(samples[:10]) # For now we just retrun 10 samples to see if the pipeline is working.


def get_fastq_input(wildcards, samples_dir, read1_suffix, read2_suffix):
    """
    Get input FASTQ file paths for a sample
    
    :wildcards: Sample names in this case will be the wildcard. A wild card lets you process samples with one rule
    :samples_dir: Directory of the sample
    :read1_suffix: Suffix for the forward read
    :read2_suffix: Suffic for the reverse read

    returns:
        dict: {"r1": path_to_r1,
                "r2": path_to _r2}
    """

    return {
        "r1": os.path.join(samples_dir,f"{wildcards.sample}{read1_suffix}"),
        "r2": os.path.join(samples_dir,f"{wildcards.sample}{read2_suffix}")
    }

#get_samples("/lunarc/nobackup/projects/snic2019-34-3/shared_elhaik_lab1/Projects/Microbiome/Mixed2025/fastq_files", \
# '_R1.fastq.gz')

    


