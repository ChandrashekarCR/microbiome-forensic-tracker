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
        merged_reads = os.path.join(RESULTS_DIR, "12_merged_reads","{sample}_aligned.fastq.gz"),
        unmerged_reads = os.path.join(RESULTS_DIR, "12_merged_reads", "{sample}_unaligned.fastq.gz")
    
    log:
        merge_log = os.path.join(RESULTS_DIR, "12_merged_reads", "{sample}.log")
    
    threads:
        config['resources']['pandaseq']['threads']
    
    resources:
        mem_mb = config['resources']['pandaseq']['mem_mb'],
        runtime = config['resources']['pandaseq']['runtime_min']
    
    params:
        output_dir = os.path.join(RESULTS_DIR, "12_merged_reads"),
        pandaseq = TOOLS["pandaseq"],
        bind_paths = lambda w: _apptainer_binds([RESULTS_DIR]),
        temp_merged_reads = os.path.join(RESULTS_DIR, "12_merged_reads","{sample}_aligned.fastq"),
        temp_unmerged_reads = os.path.join(RESULTS_DIR, "12_merged_reads","{sample}_unaligned.fastq")
    
    shell:
        """
        mkdir -p {params.output_dir}

        apptainer exec {params.bind_paths} {params.pandaseq} pandaseq \
            -f {input.r1} \
            -r {input.r2} \
            -g {log.merge_log} \
            -w {params.temp_merged_reads} \
            -u {params.temp_unmerged_reads} \
            -T {threads} \
            -F
        
        echo "Zipping the files."
        gzip -c {params.temp_merged_reads} > {output.merged_reads} && rm -f {params.temp_merged_reads}
        gzip -c {params.temp_unmerged_reads} > {output.unmerged_reads} && rm -f {params.temp_unmerged_reads}
        echo "Merged reads for {wildcards.sample}"
        """