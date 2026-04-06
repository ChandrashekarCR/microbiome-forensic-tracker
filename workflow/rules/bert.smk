"""
BERT-S rules:
    - We use the assembled reads from MEGAHIT to obtain DNABERT-S embeddings.

"""


rule dnaberts_embeddings:
    input:
        assembled_contigs=os.path.join(RESULTS_DIR, "06_assembly", "{sample}", "{sample}.fa"),
    output:
        embeddings_json=os.path.join(RESULTS_DIR, "12_dnaberts", "{sample}", "{sample}_embeddings.json"),
    log:
        os.path.join(RESULTS_DIR, "12_dnaberts", "{sample}", "dnaberts_{sample}.log"),
    threads: config["resources"]["dnaberts_embeddings"]["threads"]
    resources:
        mem_mb=config["resources"]["dnaberts_embeddings"]["mem_mb"],
        runtime=config["resources"]["dnaberts_embeddings"]["runtime_min"],
    params:
        out_dir=lambda w, output: os.path.dirname(output.embeddings_json),
        script="src/smk_helper/dnaberts_embeddings.py",
        batch_size=config["parameters"]["dnaberts_embeddings"].get("batch_size", 128),
        max_length=config["parameters"]["dnaberts_embeddings"].get("max_length", 512),
        overlap=config["parameters"]["dnaberts_embeddings"].get("overlap", 0.5),
        cuda=config["parameters"]["dnaberts_embeddings"].get("device", "cuda"),
        venv_path=config["parameters"]["dnaberts_embeddings"].get("venv_path", os.path.expanduser("~/.venv-dnaberts")),
    shell:
        """
        # Activate environment
        source {params.venv_path}/bin/activate

        # Create output directory
        mkdir -p {params.out_dir}

        # Run DNABERT-S embeddings
        python3 {params.script} \
            -i {input.assembled_contigs} \
            -o {output.embeddings_json} \
            -b {params.batch_size} \
            -m {params.max_length} \
            -l {params.overlap} \
            -d {params.cuda} > {log} 2>&1
        
        """
