"""
Post processing rules:
    - standardize_bracken: Normalize per sample bracken ouput to a csv file
    - merge_bracken: Merge all samples into one table per rank 
"""

# Step 11: Rule Standardize Bracken
rule standardize_bracken:
    input:
        bracken_report = os.path.join(RESULTS_DIR,"09_bracken","{sample}","{rank}.tsv")

    output:
        std_bracken_report = os.path.join(RESULTS_DIR,"10_standardized_bracken","{sample}_{rank}.csv")
    
    params:
        out_dir = os.path.join(RESULTS_DIR,"10_standardized_bracken"),
        min_abd = 0.001
    
    run:
        os.makedirs(str(params.out_dir), exist_ok=True)
        standardize_bracken(str(input.bracken_report),str(params.out_dir),float(params.min_abd))

# Step 12: Merge standardized Bracken reports by rank
rule merge_bracken:
    input:
        lambda wildcards: expand(os.path.join(RESULTS_DIR,"10_standardized_bracken","{sample}_{rank}.csv"), 
                                sample=SAMPLES, rank=wildcards.rank)
    output:
        merged_report = os.path.join(RESULTS_DIR,"11_final_reports","kraken_bracken_{rank}.csv")
    
    params:
        out_dir = os.path.join(RESULTS_DIR,"11_final_reports")
    
    run:
        os.makedirs(str(params.out_dir), exist_ok=True)
        concat_tables(list(input), str(output.merged_report))