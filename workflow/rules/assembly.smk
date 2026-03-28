"""
Assembly rules optimized for gut/oral metagenomics (Malmo cohort):
    - megahit_assembly: de novo assembly with meta-sensitive preset
        Produces contigs for DNA-BERT-S embedding -> geolocation prediction features.
    - filter_contigs: Keep 1000 - 10,000 bp contigs for DNA-BERT-S.
        Per the DNA-BERT-S paper, F1 improves significantly from 1024 bp to 8192 bp;
        contigs outside this window are discarded.
    - quast_assembly_qc: assembly quality assessment
"""

rule megahit_assembly:
    input:
        r1 = os.path.join(RESULTS_DIR, "05_error_correction", "{sample}_R1_corrected.fastq.gz"),
        r2 = os.path.join(RESULTS_DIR, "05_error_correction", "{sample}_R2_corrected.fastq.gz")
    output:
        contigs  = os.path.join(RESULTS_DIR, "06_assembly", "{sample}", "{sample}.fa"),
        log_file = os.path.join(RESULTS_DIR, "06_assembly", "{sample}", "log")
    log:
        megahit_log = os.path.join(RESULTS_DIR, "06_assembly", "{sample}.log")
    threads:
        config['resources']['megahit']['threads']
    resources:
        mem_mb  = config['resources']['megahit']['mem_mb'],
        runtime = config['resources']['megahit']['runtime_min']
    params:
        megahit = TOOLS['megahit'],
        contigs = os.path.join(RESULTS_DIR, "06_assembly", "{sample}", "final.contigs.fa"),
        output_dir     = os.path.join(RESULTS_DIR, "06_assembly", "{sample}"),
        min_contig_len = config['parameters']['megahit']['min_contig_len'],
        # Store k_list as a plain string - commas in the value confuse
        # Snakemake's shell string formatter (it tries tuple indexing).
        # Wrapping in a lambda bypasses the formatter safely.
        k_list = config['parameters']['megahit']['k_list'],
        min_count = config['parameters']['megahit']['min_count'],
        memory_bytes = lambda wildcards, resources: int(resources.mem_mb * 0.9 * 1e6),
        bind_paths = lambda w: _apptainer_binds([RESULTS_DIR])
    shell:
        """
        # Megahit refuses to run if the output directory already exists
        rm -rf {params.output_dir}

        echo "Starting MEGAHIT Assembly for {wildcards.sample}" > {log.megahit_log}
        echo "K-list: {params.k_list}" >> {log.megahit_log}

        # Create a temporary diretory
        # Prefer SLURM's local NVMe scratch ($TMPDIR) for MEGAHIT temp files.
        # MEGAHIT does frequent random-access I/O on its SdBG; local disk is
        # orders of magnitude faster than GPFS/Lustre network storage.
        # Fall back to a subdirectory of the output dir if $TMPDIR is not set.
        #
        # IMPORTANT: $TMPDIR is on the host at /local/slurmtmp.JOBID — it does
        # NOT exist inside the Apptainer container by default. We must bind it
        # explicitly with --bind so MEGAHIT's Python tempfile.mkdtemp() can
        # create subdirectories inside it from within the container.
        TMP_DIR=${{TMPDIR:-{params.output_dir}_tmp}}
        mkdir -p $TMP_DIR

        apptainer exec --bind $TMP_DIR:$TMP_DIR {params.bind_paths} {params.megahit} megahit \
            -1 {input.r1} \
            -2 {input.r2} \
            --out-dir {params.output_dir} \
            --tmp-dir $TMP_DIR \
            --k-list {params.k_list} \
            --min-count {params.min_count} \
            --min-contig-len {params.min_contig_len} \
            --num-cpu-threads {threads} \
            --memory {params.memory_bytes} \
            --verbose >> {log.megahit_log} 2>&1
        
        echo "Renaming the final.contigs.fa as {wildcards.sample}.fa"
        mv {params.contigs} {output.contigs}
        echo "Assembly complete for {wildcards.sample}" >> {log.megahit_log}
        """