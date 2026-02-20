# These are some of the common functions that the metagenomics pipeline uses

# Import libraries
import os
import glob

def get_fastq_samples(samples_dir, read1_suffix, read2_suffix):
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
    for file in files:
        #print(os.path.basename(file))
        basename = os.path.basename(file)
        sample_name = basename.replace(read1_suffix,"")
        #forward_read = file
        #reverse_read = os.path.join(samples_dir, f"{sample_name}{read2_suffix}")
        #samples.append([(forward_read,reverse_read)]) # For now we just retrun 5 samples to see if the pipeline is working.
        samples.append(sample_name)
    return samples



#get_fastq_samples("/lunarc/nobackup/projects/snic2019-34-3/shared_elhaik_lab1/Projects/Microbiome/Malmo2025/fastq_files", 'R1.fastq.gz','R2.fastq.gz')
    
#DATA_DIR = "/lunarc/nobackup/projects/snic2019-34-3/shared_elhaik_lab1/Projects/Microbiome/Malmo2025/fastq_files/"
#SAMPLES = get_fastq_samples(DATA_DIR, '_R1.fastq.gz','_R2.fastq.gz')[:5]
#print(SAMPLES)
