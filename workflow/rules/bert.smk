"""
BERT-S rules:
    - merge_reads: Merge the forward and reverse reads
    - dereplication: We do not need BERT-S embeddings for repeated or duplicated sequences. There can be a problem when we have the
        same read (for example kinases coding part) present in all the samples in all species and they will have the same embedding.
        This should not be the case, becuase we need to have an embedding which is different? Need to think about this part in detail.

"""
rule merge_reads:
    input:
        r1 = lambda w: os.path.join(RESULTS_DIR, "05_error_correction", f"{w.sample}_R1_corrected.fastq.gz"),
        r2 = lambda w: os.path.join(RESULTS_DIR, "05_error_correction", f"{w.sample}_R2_corrected.fastq.gz")
    
    output:
        merged_reads = os.path.join(RESULTS_DIR, "12_merged_reads","{sample}_aligned.fastq"),
        unmerged_reads = os.path.join(RESULTS_DIR, "12_merged_reads", "{sample}_unaligned.fastq")
    
    log:
        merge_log = os.path.join(RESULTS_DIR, "12_merged_reads", "{sample}.log")
    
    threads:
        pass
    
    resources:
        pass
    
    params:
        output_dir = os.path.join(RESULTS_DIR, "12_merged_reads"),
        pandaseq = TOOLS["pandaseq"],
    
    shell:
        """
        mkdir -p {params.output_dir}

        
        
        """