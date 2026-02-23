"""
Preprocessing rules:
    - fastp: Qulaity filtering + poly G trimming
    - adapter_removal: AdapterRemoval2
    - remove_human_reads: Bowtie2 host depletion
    - error_correction: Tadpole/ BBduk fallback
"""

# Step 2 - fastp (Quality filtering and adapter trimming)
# Qualified Quality Phred: 30
# trim_poly_g
# dont_eval_duplication
# Here we perform remive reads if their quality is less than 30 and remove the polyG tails
rule fastp:
    input:
        r1 = lambda w: os.path.join(DATA_DIR, f"{w.sample}_R1.fastq.gz"),
        r2 = lambda w: os.path.join(DATA_DIR, f"{w.sample}_R2.fastq.gz")
    output:
        r1_out = os.path.join(RESULTS_DIR, "02_fastp", "{sample}_out_R1.fastq.gz"),
        r2_out = os.path.join(RESULTS_DIR, "02_fastp", "{sample}_out_R2.fastq.gz"),
        html = os.path.join(RESULTS_DIR, "02_fastp", "{sample}.fastp.html"),
        json = os.path.join(RESULTS_DIR, "02_fastp", "{sample}.fastp.json")
    log:
        os.path.join(RESULTS_DIR, "02_fastp", "{sample}.log")

    threads:
        config['resources']['fastp']['threads']

    resources:
        mem_mb = config['resources']['fastp']['mem_mb'],
        runtime = config['resources']['fastp']['runtime_min']

    params:
        fastp = TOOLS['fastp'],
        output_dir = f"{RESULTS_DIR}/02_fastp",
        quality = config['parameters']['fastp']['qualified_quality_phred'],
        trim_poly_g = "--trim_poly_g" if config['parameters']['fastp']['trim_poly_g'] else "",
        dont_eval_dup = "--dont_eval_duplication" if config['parameters']['fastp']['dont_eval_duplication'] else "",
        bind_paths = lambda w: _apptainer_binds(
            [
                SAMPLE_DF.loc[w.sample, "r1"],
                SAMPLE_DF.loc[w.sample, "r2"],
                os.path.join(RESULTS_DIR, "02_fastp")
            ]
        )
    
    shell: 
        """
        # Create output directory
        mkdir -p {params.output_dir}
        
        echo "Running fastp on {wildcards.sample}..."
        
        # Run fastp with bind mounts - SEPARATE R1/R2 processing
        apptainer exec {params.bind_paths} {params.fastp} \
             fastp \
                --in1 {input.r1} \
                --in2 {input.r2} \
                --out1 {output.r1_out} \
                --out2 {output.r2_out} \
                --html {output.html} \
                --json {output.json} \
                {params.dont_eval_dup} \
                --qualified_quality_phred {params.quality} \
                --thread {threads} \
                {params.trim_poly_g} &> {log}
        
        echo "fastp completed successfully for {wildcards.sample}"
        """

# Step3
rule adapter_removal:
    input:
        r1 = lambda w: os.path.join(RESULTS_DIR, "02_fastp", f"{w.sample}_out_R1.fastq.gz"),
        r2 = lambda w: os.path.join(RESULTS_DIR, "02_fastp", f"{w.sample}_out_R2.fastq.gz")

    output:
        trimmed_r1 = os.path.join(RESULTS_DIR, "03_trimmed", "{sample}_trimmed_R1.fastq.gz"),
        trimmed_r2 = os.path.join(RESULTS_DIR, "03_trimmed", "{sample}_trimmed_R2.fastq.gz"),
        settings = os.path.join(RESULTS_DIR, "03_trimmed", "{sample}.settings"),
        discarded = os.path.join(RESULTS_DIR, "03_trimmed", "{sample}.discarded.fastq.gz"),
        singleton = os.path.join(RESULTS_DIR, "03_trimmed", "{sample}.singleton.fastq.gz")

    threads:
        config['resources']['adapter_removal']['threads']

    resources:
        mem_mb = config['resources']['adapter_removal']['mem_mb'],
        runtime = config['resources']['adapter_removal']['runtime_min']

    params:
        adapter_removal = TOOLS['adapter_removal'],
        output_dir = f"{RESULTS_DIR}/03_trimmed",
        prefix = os.path.join(RESULTS_DIR,"03_trimmed","{sample}"),
        common_adapters = COMMON_ADAPTERS, #os.path.join(ROOT_DIR,"bin","common_adapters.txt") 
        trimns_flag = "--trimns" if config['parameters']['adapter_removal']['trimns'] else '',
        trimqualities_flag = "--trimqualities" if config['parameters']['adapter_removal']['trimqualities'] else '',
        bind_paths = lambda w: _apptainer_binds([RESULTS_DIR])

    shell:
        """
        mkdir -p {params.output_dir}
        
        echo "Running Adapter Removal on {wildcards.sample}"
        # Run the adapter removal command
        apptainer exec {params.bind_paths} {params.adapter_removal} AdapterRemoval \
                --gzip \
                --file1 {input.r1} \
                --file2 {input.r2} \
                --output1 {output.trimmed_r1} \
                --output2 {output.trimmed_r2} \
                --discarded {params.prefix}.discarded.fastq.gz \
                --singleton {params.prefix}.singleton.fastq.gz \
                --settings {params.prefix}.settings \
                --adapter-list {params.common_adapters} \
                {params.trimns_flag} \
                {params.trimqualities_flag} \
                --threads {threads}

        echo "Adapter Removal completeed sucessfully for {wildcards.sample}"
        
        """

# Step 5 - Removal of Human Reads
rule remove_human_reads:
    input:
        # Filter reads
        r1 = lambda w: os.path.join(RESULTS_DIR,"03_trimmed",f"{w.sample}_trimmed_R1.fastq.gz"),
        r2 = lambda w: os.path.join(RESULTS_DIR,"03_trimmed", f"{w.sample}_trimmed_R2.fastq.gz")

    output:
        r1 = os.path.join(RESULTS_DIR, "04_host_removed", "{sample}_R1_clean.fastq.gz"),
        r2 = os.path.join(RESULTS_DIR, "04_host_removed", "{sample}_R2_clean.fastq.gz")

    threads:
        config['resources']['bowtie2']['threads']

    resources:
        mem_mb = config['resources']['bowtie2']['mem_mb'],
        runtime = config['resources']['bowtie2']['runtime_min']

    params:
        bowtie2 = TOOLS['bowtie2'],
        output_dir = f"{RESULTS_DIR}/04_host_removed",
        host_genome = HOST_GENOME,
        sensitivity = f"--{config['parameters']['bowtie2']['sensitivity']}",
        bind_paths = lambda w: _apptainer_binds([RESULTS_DIR, HOST_GENOME])
    
    log:
        os.path.join(RESULTS_DIR, "04_host_removed", "{sample}.log")

    shell:
        """
        mkdir -p {params.output_dir}

        apptainer exec {params.bind_paths} {params.bowtie2} bowtie2 \
                {params.sensitivity} \
                --threads {threads} \
                -x {params.host_genome} \
                --un-conc-gz {params.output_dir}/{wildcards.sample}_clean \
                -1 {input.r1} \
                -2 {input.r2} \
                > {params.output_dir}/{wildcards.sample}.sam 2> {log}
        
        rm {params.output_dir}/{wildcards.sample}.sam 
        mv {params.output_dir}/{wildcards.sample}_clean.1 {output.r1}
        mv {params.output_dir}/{wildcards.sample}_clean.2 {output.r2}

        echo "Removed Human reads from the microbiome"                 
        """

# Step 6: Error correction using tadpole
# srun --partition=lu48 --cpus-per-task=24 --mem=128G --time=01:0:00 --pty bash
# This much amount of reources is needed for error correction to run smoothly
rule error_correction:
    input:
        r1 = os.path.join(RESULTS_DIR, "04_host_removed", "{sample}_R1_clean.fastq.gz"),
        r2 = os.path.join(RESULTS_DIR, "04_host_removed", "{sample}_R2_clean.fastq.gz")
    output:
        r1 = os.path.join(RESULTS_DIR, "05_error_correction", "{sample}_R1_corrected.fastq.gz"),
        r2 = os.path.join(RESULTS_DIR, "05_error_correction", "{sample}_R2_corrected.fastq.gz")
    log:
        repair  = os.path.join(RESULTS_DIR, "05_error_correction", "{sample}_tmp.log"),
        tadpole = os.path.join(RESULTS_DIR, "05_error_correction", "{sample}_corrected.log")
    threads:
        config["resources"]["error_correction"]["threads"]
    resources:
        mem_mb  = config["resources"]["error_correction"]["mem_mb"],
        runtime = config["resources"]["error_correction"]["runtime_min"]
    params:
        tmp_r1     = os.path.join(RESULTS_DIR, "05_error_correction", "{sample}_tmp_R1.fastq.gz"),
        tmp_r2     = os.path.join(RESULTS_DIR, "05_error_correction", "{sample}_tmp_R2.fastq.gz"),
        tadpole    = TOOLS["tadpole"],
        repair     = TOOLS["repair"],
        bbduk      = TOOLS["bbduk"],
        output_dir = os.path.join(RESULTS_DIR, "05_error_correction"),
        memory_gb  = config["parameters"]["error_correction"]["memory_gb"],
        k_size     = config["parameters"]["error_correction"]["k_size"],
        ecc        = "ecc=t"        if config["parameters"]["error_correction"]["ecc"]        else "ecc=f",
        reassemble = "reassemble=t" if config["parameters"]["error_correction"]["reassemble"] else "reassemble=f",
        conservative="conservative=t" if config["parameters"]["error_correction"]["conservative"] else "conservative=f"
    shell:
        """
        mkdir -p {params.output_dir}

        # Step 1: Repair paired-end reads
        {params.repair} \
            in={input.r1} in2={input.r2} \
            out={params.tmp_r1} out2={params.tmp_r2} \
            repair=t -Xmx{params.memory_gb}g -eoom > {log.repair} 2>&1

        if [ ! -s "{params.tmp_r1}" ] || [ ! -s "{params.tmp_r2}" ]; then
            echo "ERROR: repair.sh produced empty output" >&2; exit 1
        fi

        echo "Starting error correction for {wildcards.sample}" > {log.tadpole}

        # Attempt 1: conservative tadpole
        if {params.tadpole} mode=correct \
                in={params.tmp_r1} in2={params.tmp_r2} \
                out={output.r1} out2={output.r2} \
                -Xmx{params.memory_gb}g threads={threads} buildthreads={threads} \
                k={params.k_size} {params.conservative} prealloc=f \
                {params.ecc} {params.reassemble} pincer=f tail=f >> {log.tadpole} 2>&1; then
            echo "Attempt 1 (conservative tadpole) succeeded" >> {log.tadpole}
            rm -f {params.tmp_r1} {params.tmp_r2}

        # Attempt 2: minimal tadpole
        elif {params.tadpole} mode=correct \
                in={params.tmp_r1} in2={params.tmp_r2} \
                out={output.r1} out2={output.r2} \
                -Xmx12g threads=1 buildthreads=1 k=21 \
                conservative=t prealloc=f ecc=t reassemble=f >> {log.tadpole} 2>&1; then
            echo "Attempt 2 (minimal tadpole) succeeded" >> {log.tadpole}
            rm -f {params.tmp_r1} {params.tmp_r2}

        # Attempt 3: BBDuk
        elif {params.bbduk} \
                in={params.tmp_r1} in2={params.tmp_r2} \
                out={output.r1} out2={output.r2} \
                mode=correct ecc=t aggressive=f -Xmx8g threads=1 >> {log.tadpole} 2>&1; then
            echo "Attempt 3 (BBDuk) succeeded" >> {log.tadpole}
            rm -f {params.tmp_r1} {params.tmp_r2}

        # Fallback: pass repaired reads through unchanged
        else
            echo "All correction methods failed — using repaired reads" >> {log.tadpole}
            cp {params.tmp_r1} {output.r1}
            cp {params.tmp_r2} {output.r2}
            rm -f {params.tmp_r1} {params.tmp_r2}
        fi

        if [ ! -s "{output.r1}" ] || [ ! -s "{output.r2}" ]; then
            echo "CRITICAL: output files are empty or missing" >&2; exit 1
        fi
        echo "Error correction complete for {wildcards.sample}" >> {log.tadpole}
        """