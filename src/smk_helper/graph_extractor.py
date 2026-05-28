# This script will be used as snakmake rule to process kraken and bracken reports
# per sample to generate a graph data strucutre for organisms across the lineage

# Import Libraries
import os
import pandas as pd
import numpy as np
import networkx as nx
from pathlib import Path


class TaxGraph:
    def __init__(self, kraken_report: str, bracken_dir: str):
        self.kraken_report = kraken_report
        self.bracken_dir = bracken_dir

        # Read the bracken files from directory and convert them to pandas dataframe
        self.bracken_df = pd.DataFrame()
        for files in os.listdir(self.bracken_dir):
            # Lineage dataframe with RSA
            lin_df = pd.read_csv(f"{self.bracken_dir}/{files}",sep="\t")

            # Concatenate with bracken_df
            self.bracken_df = pd.concat([self.bracken_df,lin_df],axis=0)
        
        # Make the naming compatible with kraken reports
        self.bracken_df = self.bracken_df.rename(columns={'taxonomy_id':'tax_id'})

        # Read kraken as a dataframe
        columns = ["precent","clade_reads","direct_reads","rank","tax_id","name"]
        self.kraken_df = pd.read_csv(self.kraken_report,sep="\t",names=columns, header=None)
    
    def filter_bracken_df(self, min_abd: float = 0.0001) -> pd.DataFrame:
        return self.bracken_df[self.bracken_df['fraction_total_reads'] >= min_abd ]

    def lineage_from_kraken(self) -> list[tuple[int,int]]:
        # Set lists for nodes and edges
        nodes = []
        edges= []

        # stack entries: (depth, tax_id)
        stack: list[tuple[int, int]] = []

        with open(self.kraken_report,"r") as f_in:
            for line in f_in:
                line = line.rstrip("\n")
                if not line.strip():
                    continue
                parts = line.split("\t") # Should expect 6 columns
                if len(parts) < 6:
                    continue
                
                pct_clade = float(parts[0].strip()) # Percent of classified reads
                clade_reads = int(parts[1].strip()) # Assigned reads to that clade
                direct_reads = int(parts[2].strip()) # Assigned reads to that particular name in that clade
                rank_code = parts[3].strip() # Phylum (P), Class (C), Order (O), Family(F), Genus(G), Species(S). There can be P1,P2,C1,C2...
                tax_id = int(parts[4].strip()) # Unique taxonomic id
                name = parts[5] # Name of the organism. This will have leading spaces -> useful for getting lineage


                # Depth = number of leading spaces / 2
                n_spaces = len(name) - len(name.lstrip(" "))
                depth = n_spaces // 2
                # After we get the depth from the root, we will strip the name
                name = name.strip()
                #print(tax_id,name,rank_code,clade_reads,n_spaces,depth)

                # Pop the stack until we find the correct parent level
                while stack and stack[-1][0] >= depth:
                    stack.pop()

                # Determine parent BEFORE adding node
                parent_tax_id = stack[-1][1] if stack else None

                # Add node attributes
                nodes.append({
                        "tax_id":       tax_id,
                        "name":         name,
                        "rank":         rank_code,
                        "depth":        depth,
                        "parent_tax_id": parent_tax_id,
                    })

                if parent_tax_id is not None:
                    edges.append((parent_tax_id, tax_id))

                # Push current node onto stack
                stack.append((depth,tax_id))
        return nodes,edges
        



kraken_report = "/home/chandru/lu2025-12-38/Students/chandru/assembly_testing/08_kraken2/zr23059_137/kraken_report.tsv"
bracken_dir = "/home/chandru/lu2025-12-38/Students/chandru/assembly_testing/09_bracken/zr23059_137"
G = TaxGraph(kraken_report,bracken_dir)
print(G.filter_bracken_df())
print(G.lineage_from_kraken())