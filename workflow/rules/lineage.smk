"""
Lineage rules:
    - extract_taxonomy: Extract the PCOFGS information from the kraken reports and the RSA from bracken directory
    Store all this information in graph data structure.
"""


# Step 13: Rule Extract Taxonomy
rule extract_taxonomy:
    input:
        bracken_dir=os.path.join(RESULTS_DIR, "09_bracken", "{sample}", "species.tsv"),  # We just access this file, but use the directory instead, else it will break the logic
        kraken_report=os.path.join(
            RESULTS_DIR, "08_kraken2", "{sample}", "kraken_report.tsv"
        ),
    output:
        nodes_output=os.path.join(RESULTS_DIR, "13_taxgraph", "{sample}", "nodes.csv"),
        edges_output=os.path.join(RESULTS_DIR, "13_taxgraph", "{sample}", "edges.csv"),
    resources:
        mem_mb=config["resources"]["taxgraph"]["mem_mb"],
        runtime=config["resources"]["taxgraph"]["runtime_min"],
    params:
        out_dir=lambda w, output: os.path.dirname(output.nodes_output),
        graph_extractor_script=config["parameters"]["taxgraph"]["path"],
        bracken_dir=lambda w: os.path.join(RESULTS_DIR, "09_bracken", w.sample),
    shell:
        """
        mkdir -p {params.out_dir}

        python3 {params.graph_extractor_script} \
            --kraken_report {input.kraken_report} \
            --bracken_dir {params.bracken_dir} \
            --output_dir {params.out_dir}
        """
