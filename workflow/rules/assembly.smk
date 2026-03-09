"""
Assembly rules optimized for gut/oral metagenomics (Malmo cohort):
    - megahit_assembly: de novo assembly with meta-sensitive preset
        Produces contigs for DNA-BERT-S embedding → geolocation prediction features.
    - filter_contigs: Keep 1000–10 000 bp contigs for DNA-BERT-S.
        Per the DNA-BERT-S paper, F1 improves significantly from 1024 bp to 8192 bp;
        contigs outside this window are discarded.
    - quast_assembly_qc: assembly quality assessment
"""

rule megahit_assembly:
    input:
        r1 = os.path.join(RESULTS_DIR, "05_error_correction", "{sample}_R1_corrected.fastq.gz"),
        r2 = os.path.join(RESULTS_DIR, "05_error_correction", "{sample}_R2_corrected.fastq.gz")
    output:
        contigs  = os.path.join(RESULTS_DIR, "06_assembly", "{sample}", "final.contigs.fa"),
        log_file = os.path.join(RESULTS_DIR, "06_assembly", "{sample}", "log")
    log:
        megahit_log = os.path.join(RESULTS_DIR, "06_assembly", "{sample}.log")
    threads:
        config['resources']['megahit']['threads']
    resources:
        mem_mb  = config['resources']['megahit']['mem_mb'],
        runtime = config['resources']['megahit']['runtime_min']
    params:
        megahit        = TOOLS['megahit'],
        output_dir     = os.path.join(RESULTS_DIR, "06_assembly", "{sample}"),
        min_contig_len = config['parameters']['megahit']['min_contig_len'],
        preset         = config['parameters']['megahit']['preset'],
        min_count      = config['parameters']['megahit']['min_count'],
        # MEGAHIT --memory accepts a fraction (0–1 = % of machine RAM) OR
        # absolute bytes (>1). We pass 90% of the SLURM allocation as bytes
        # so the OS, I/O buffers, and C++ runtime have the remaining 10%.
        memory_bytes   = lambda wildcards, resources: int(resources.mem_mb * 0.9 * 1e6),
        bind_paths     = lambda w: _apptainer_binds([RESULTS_DIR])
    shell:
        """
        # MEGAHIT refuses to run if the output directory already exists.
        rm -rf {params.output_dir}

        echo "Starting MEGAHIT assembly for {wildcards.sample}" > {log.megahit_log}
        echo "Preset   : {params.preset}" >> {log.megahit_log}
        echo "  -> sets k-list automatically; do NOT also pass --k-list" >> {log.megahit_log}
        echo "Min-count: {params.min_count}" >> {log.megahit_log}
        echo "Memory   : {params.memory_bytes} bytes | Threads: {threads}" >> {log.megahit_log}

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
        mkdir -p "$TMP_DIR"

        apptainer exec --bind "$TMP_DIR:$TMP_DIR" {params.bind_paths} {params.megahit} megahit \
            -1 {input.r1} \
            -2 {input.r2} \
            --out-dir         {params.output_dir} \
            --tmp-dir         "$TMP_DIR" \
            --presets         {params.preset} \
            --min-count       {params.min_count} \
            --min-contig-len  {params.min_contig_len} \
            --num-cpu-threads {threads} \
            --memory          {params.memory_bytes} \
            --verbose >> {log.megahit_log} 2>&1

        # Only clean up the fallback tmp dir; SLURM removes $TMPDIR automatically.
        if [ "$TMP_DIR" = "{params.output_dir}_tmp" ]; then
            rm -rf "$TMP_DIR"
        fi

        # Fail fast — do not continue to stats if assembly is empty.
        if [ ! -s {output.contigs} ]; then
            echo "ERROR: MEGAHIT produced empty contigs for {wildcards.sample}" >&2
            exit 1
        fi

        # Post-assembly statistics
        # Contig file is typically 10–500 MB (much smaller than inputs), so
        # reading it twice for stats is fast.
        num_contigs=$(grep -c "^>" {output.contigs})
        total_bp=$(awk '/^>/{{next}} {{sum += length($0)}} END {{print sum+0}}' {output.contigs})

        # N50: compute all lengths once, sort descending, walk until cumsum >= total/2
        CONTIG_LENGTHS=$(awk '/^>/{{if(seq) print length(seq); seq=""}} \
                              !/^>/{{seq=seq$0}} \
                              END{{if(seq) print length(seq)}}' {output.contigs} | sort -rn)
        N50=$(echo "$CONTIG_LENGTHS" | \
              awk -v tot="$total_bp" 'BEGIN{{s=0}} {{s+=$1; if(s>=tot/2){{print $1; exit}}}}')
        longest=$(echo "$CONTIG_LENGTHS" | head -1)

        echo "Total contigs: $num_contigs"        >> {log.megahit_log}
        echo "Total bases  : $total_bp bp"        >> {log.megahit_log}
        echo "N50          : ${{N50:-NA}} bp"     >> {log.megahit_log}
        echo "Longest      : ${{longest:-NA}} bp" >> {log.megahit_log}
        echo "Assembly complete for {wildcards.sample}" >> {log.megahit_log}
        """