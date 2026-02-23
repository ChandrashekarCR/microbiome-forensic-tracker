"""
BERT-S rules:
    - merge_reads: Merge the forward and reverse reads
    - dereplication: We do not need BERT-S embeddings for repeated or duplicated sequences

"""
rule merge_reads:
    input:
        r1 = lambda w: os.path.join(RESULTS_DIR, f"{w.sample}_R1.fastq.gz"),
        r2 = lambda w: os.path.join(RESULTS_DIR, f"{w.sample}_R2.fastq.gz")
    
    output:
        merged_reads = os.path.join(RESULTS_DIR,"")