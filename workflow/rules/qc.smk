"""
QC rules:
    - fastqc_raw: FASTQC on raw reads
    - fastqc_processed: FASTQC on processed reads
    - multiqc: Aggregrate QC report on the preprocecssing steps
"""


# Step 1: FASTQC raw
rule fastqc_raw:
    input:
        r1=lambda w: os.path.join(DATA_DIR, f"{w.sample}_R1.fastq.gz"),
        r2=lambda w: os.path.join(DATA_DIR, f"{w.sample}_R2.fastq.gz"),
    output:
        # HTML and zip files
        html_r1=os.path.join(RESULTS_DIR, "01_fastqc_raw", "{sample}_R1_fastqc.html"),
        zip_r1=os.path.join(RESULTS_DIR, "01_fastqc_raw", "{sample}_R1_fastqc.zip"),
        html_r2=os.path.join(RESULTS_DIR, "01_fastqc_raw", "{sample}_R2_fastqc.html"),
        zip_r2=os.path.join(RESULTS_DIR, "01_fastqc_raw", "{sample}_R2_fastqc.zip"),
    log:
        os.path.join(RESULTS_DIR, "01_fastqc_raw", "{sample}.log"),
    threads: config["resources"]["fastqc"]["threads"]
    resources:
        mem_mb=config["resources"]["fastqc"]["mem_mb"],
        runtime=config["resources"]["fastqc"]["runtime_min"],
    params:
        fastqc=TOOLS["fastqc"],
        output_dir=lambda w, output: os.path.dirname(output.html_r1),
        bind_paths=lambda w: _apptainer_binds(
            [
                SAMPLE_DF.loc[w.sample, "r1"],
                SAMPLE_DF.loc[w.sample, "r2"],
                os.path.join(RESULTS_DIR, "01_fastqc_raw"),
            ]
        ),
    shell:
        """
        # Create output directory
        mkdir -p {params.output_dir}     
        
        echo "Running FastQC on {wildcards.sample}..."
        
        # Run FastQC with bind mounts for /lunarc/nobackup
        apptainer exec {params.bind_paths} {params.fastqc} \
            fastqc {input.r1} {input.r2} -o {params.output_dir} -t {threads}
        
        echo "FastQC completed successfully for {wildcards.sample}"
        """


# Step 7: FASTQC Processed reads
rule fastqc_processed:
    input:
        r1=lambda w: os.path.join(RESULTS_DIR, "05_error_correction", f"{w.sample}_R1_corrected.fastq.gz"),
        r2=lambda w: os.path.join(RESULTS_DIR, "05_error_correction", f"{w.sample}_R2_corrected.fastq.gz"),
    output:
        # HTML and zip files
        html_r1=os.path.join(RESULTS_DIR, "06_fastqc_post", "{sample}_R1_corrected_fastqc.html"),
        zip_r1=os.path.join(RESULTS_DIR, "06_fastqc_post", "{sample}_R1_corrected_fastqc.zip"),
        html_r2=os.path.join(RESULTS_DIR, "06_fastqc_post", "{sample}_R2_corrected_fastqc.html"),
        zip_r2=os.path.join(RESULTS_DIR, "06_fastqc_post", "{sample}_R2_corrected_fastqc.zip"),
    log:
        os.path.join(RESULTS_DIR, "06_fastqc_post", "{sample}.log"),
    threads: config["resources"]["fastqc"]["threads"]
    resources:
        mem_mb=config["resources"]["fastqc"]["mem_mb"],
        runtime=config["resources"]["fastqc"]["runtime_min"],
    params:
        fastqc=TOOLS["fastqc"],
        output_dir=lambda w, output: os.path.dirname(output.html_r1),
        bind_paths=lambda w: _apptainer_binds([RESULTS_DIR]),
    shell:
        """
        # Create output directory
        mkdir -p {params.output_dir}     
        
        echo "Running FastQC on {wildcards.sample}..."
        
        # Run FastQC with bind mounts for /lunarc/nobackup
        apptainer exec {params.bind_paths} {params.fastqc} \
            fastqc {input.r1} {input.r2} -o {params.output_dir} -t {threads}
        
        echo "FastQC completed successfully for {wildcards.sample}"
        """


# Step 8 - MultiQC
rule multiqc:
    input:
        # Depend on actual files, not directories
        expand(
            os.path.join(RESULTS_DIR, "01_fastqc_raw", "{sample}_{read}_fastqc.html"),
            sample=SAMPLES,
            read=READS,
        ),
        expand(
            os.path.join(RESULTS_DIR, "02_fastp", "{sample}.fastp.json"),
            sample=SAMPLES,
        ),
        expand(
            os.path.join(RESULTS_DIR, "03_trimmed", "{sample}.settings"),
            sample=SAMPLES,
        ),
        expand(
            os.path.join(RESULTS_DIR, "04_host_removed", "{sample}.log"),
            sample=SAMPLES,
        ),
        expand(
            os.path.join(RESULTS_DIR, "05_error_correction", "{sample}_corrected.log"),
            sample=SAMPLES,
        ),
        expand(
            os.path.join(RESULTS_DIR, "06_fastqc_post", "{sample}_{read}_corrected_fastqc.html"),
            sample=SAMPLES,
            read=READS,
        ),
    output:
        multiqc_report=directory(os.path.join(RESULTS_DIR, "07_multiqc")),
    log:
        os.path.join(RESULTS_DIR, "07_multiqc", "multiqc.log"),
    resources:
        mem_mb=config["resources"]["multiqc"]["mem_mb"],
        runtime=config["resources"]["multiqc"]["runtime_min"],
    params:
        multiqc=TOOLS["multiqc"],
        output_dir=lambda w, output: output.multiqc_report,
        results_dir=RESULTS_DIR,
        bind_paths=lambda w: _apptainer_binds([RESULTS_DIR]),
    shell:
        """
        mkdir -p {params.output_dir}

        apptainer exec {params.bind_paths} {params.multiqc} \
             multiqc {params.results_dir} -o {output.multiqc_report} > {log} 2>&1
        """
