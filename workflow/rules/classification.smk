"""
Classificaiton rules:
    - kraken: Kraken2 Taxonomic classification
    - bracken: Bracken abundance estimation

"""


# Step 9 - Kraken2
rule kraken:
    input:
        r1=lambda w: os.path.join(
            RESULTS_DIR, "05_error_correction", f"{w.sample}_R1_corrected.fastq.gz"
        ),
        r2=lambda w: os.path.join(
            RESULTS_DIR, "05_error_correction", f"{w.sample}_R2_corrected.fastq.gz"
        ),
    output:
        kraken=os.path.join(RESULTS_DIR, "08_kraken2", "{sample}", "kraken.tsv"),
        kraken_report=os.path.join(
            RESULTS_DIR, "08_kraken2", "{sample}", "kraken_report.tsv"
        ),
    log:
        os.path.join(RESULTS_DIR, "08_kraken2", "{sample}.log"),
    container:
        TOOLS["kraken2"]
    threads: config["resources"]["kraken2"]["threads"]
    resources:
        mem_mb=config["resources"]["kraken2"]["mem_mb"],  # 460G: core-nt DB 310G + index/buffers/OS; aurora routes to ca19-ca22 (768G) only at this size
        runtime=config["resources"]["kraken2"]["runtime_min"],
        slurm_partition=select_best_partition,  # fills: aurora(4) -> gpua40(6) -> gpua40i(6)
    params:
        out_dir=lambda w, output: os.path.dirname(output.kraken),
        database=KRAKEN2_DB,
    shell:
        """
        mkdir -p {params.out_dir}

        kraken2 \
                --db {params.database} \
                --threads {threads} \
                --report {output.kraken_report} \
                --output {output.kraken} \
                --paired {input.r1} {input.r2} > {log} 2>&1
        """


# Step 10: Bracken
rule bracken:
    input:
        kraken_report=os.path.join(
            RESULTS_DIR, "08_kraken2", "{sample}", "kraken_report.tsv"
        ),
    output:
        bracken_report=os.path.join(RESULTS_DIR, "09_bracken", "{sample}", "{rank}.tsv"),
    log:
        bracken_log=os.path.join(RESULTS_DIR, "09_bracken", "{sample}.{rank}.out"),
    container:
        TOOLS["bracken"]
    resources:
        mem_mb=config["resources"]["bracken"]["mem_mb"],
        runtime=config["resources"]["bracken"]["runtime_min"],
    params:
        database=BRACKEN_DB,
        out_dir=lambda w, output: os.path.dirname(output.bracken_report),
        rank=lambda wildcards: "{}".format(wildcards.rank)[:1].capitalize(),
        read_len=READ_LEN,
    shell:
        """
        mkdir -p {params.out_dir}

        bracken \
                -r {params.read_len} \
                -i {input.kraken_report} \
                -o {output.bracken_report} \
                -d {params.database} \
                -l {params.rank} > {log.bracken_log} 2>&1
        """
