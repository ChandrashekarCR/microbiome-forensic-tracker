# This script will be used as snakmake rule to process kraken and bracken reports
# per sample to generate a graph data strucutre for organisms across the lineage

# Import Libraries
import argparse
import os

import pandas as pd


class TaxGraph:
    def __init__(self, kraken_report: str, bracken_dir: str, min_abd: float = 0.0001):
        self.kraken_report = kraken_report
        self.bracken_dir = bracken_dir
        self.min_abd = min_abd
        # Bracken based ranks
        self.standard_ranks = {"P", "C", "O", "F", "G", "S"}

        # Read the bracken files from directory and convert them to pandas dataframe
        self.bracken_df = pd.DataFrame()
        for files in os.listdir(self.bracken_dir):
            # Lineage dataframe with RSA
            lin_df = pd.read_csv(f"{self.bracken_dir}/{files}", sep="\t")

            # Concatenate with bracken_df
            self.bracken_df = pd.concat([self.bracken_df, lin_df], axis=0)

        # Make the naming compatible with kraken reports
        self.bracken_df = self.bracken_df.rename(columns={"taxonomy_id": "tax_id"})
        # Filter RSA based on min_abd
        self.bracken_df = self.bracken_df[self.bracken_df["fraction_total_reads"] >= self.min_abd]

        # Read kraken as a dataframe
        columns = ["precent", "clade_reads", "direct_reads", "rank", "tax_id", "name"]
        self.kraken_df = pd.read_csv(self.kraken_report, sep="\t", names=columns, header=None)

    def bracken_rsa_lookup(self, df: pd.DataFrame, tax_id: int, column_name: str) -> float:
        result = df[df["tax_id"] == tax_id][column_name].values
        return result[0] if len(result) > 0 else 0.0

    def lineage_from_kraken(self) -> list[tuple[int, int]]:
        # Set lists for nodes and edges
        nodes = []
        edges = []

        # stack entries: (depth, tax_id)
        stack: list[tuple[int, int]] = []

        with open(self.kraken_report, "r") as f_in:
            for line in f_in:
                line = line.rstrip("\n")
                if not line.strip():
                    continue
                parts = line.split("\t")  # Should expect 6 columns
                if len(parts) < 6:
                    continue

                _pct_clade = float(parts[0].strip())  # Percent of classified reads
                _clade_reads = int(parts[1].strip())  # Assigned reads to that clade
                _direct_reads = int(parts[2].strip())  # Assigned reads to that particular name in that clade
                rank_code = parts[3].strip()  # Phylum (P), Class (C), Order (O), Family(F), Genus(G), Species(S). There can be P1,P2,C1,C2...
                tax_id = int(parts[4].strip())  # Unique taxonomic id
                name = parts[5]  # Name of the organism. This will have leading spaces -> useful for getting lineage

                # Depth = number of leading spaces / 2
                n_spaces = len(name) - len(name.lstrip(" "))
                depth = n_spaces // 2
                # After we get the depth from the root, we will strip the name
                name = name.strip()
                # print(tax_id,name,rank_code,clade_reads,n_spaces,depth)

                # Pop the stack until we find the correct parent level
                while stack and stack[-1][0] >= depth:
                    stack.pop()

                # Determine parent BEFORE adding node
                parent_tax_id = stack[-1][1] if stack else None

                # Add node attributes
                nodes.append(
                    {
                        "tax_id": tax_id,
                        "name": name,
                        "rank": rank_code,
                        "depth": depth,
                        "parent_tax_id": parent_tax_id,
                    }
                )

                if parent_tax_id is not None:
                    edges.append((parent_tax_id, tax_id))

                # Push current node onto stack
                stack.append((depth, tax_id))
        return nodes, edges

    def filter_nodes_edges_based_on_bracken_outputs(self, nodes: list) -> list[tuple[int, int]]:
        # Step 1: Filter to bracken report taxa only
        bracken_tax_ids = set(self.bracken_df["tax_id"].values)
        all_nodes_lookup = {n["tax_id"]: n for n in nodes}

        # Filter the nodes
        nodes_filtered = [n for n in nodes if n["tax_id"] in bracken_tax_ids]

        # Step 2: Compress lineage (There are lot of non standard ranks like P1, P2, C1, C2...)
        # These need to be skipped but the edges has to be re-calculated so that they point to bracken classifed ranks only.
        corrected_edges = []
        for node in nodes_filtered:
            child_tax_id = node["tax_id"]
            current_parent = node["parent_tax_id"]

            # If there is no parent, then we just continue
            if current_parent is None:
                continue

            # When the current parent is not None
            while current_parent is not None:
                parent_node = all_nodes_lookup.get(current_parent)
                if parent_node is None:
                    break

                parent_rank = parent_node["rank"]
                if parent_rank in self.standard_ranks and current_parent in bracken_tax_ids:
                    corrected_edges.append((current_parent, child_tax_id))
                    break

                current_parent = parent_node["parent_tax_id"]

        # Step 3: Add RSA from Bracken data frame to each node as attributes
        for organism in nodes_filtered:
            organism["rsa"] = self.bracken_rsa_lookup(self.bracken_df, organism["tax_id"], "fraction_total_reads")

        return nodes_filtered, corrected_edges

    def convert_nodes_edges_to_df(self, nodes: list, edges: list) -> list[pd.DataFrame]:
        # Convert nodes to a dataframe
        nodes_df = pd.DataFrame.from_dict(nodes)
        edges_df = pd.DataFrame(edges, columns=["parent", "child"])

        # Add RSA propogration. These are edge attributes to tell how of RSA is propogating to the further levels
        # rsa_porp = rsa_child/rsa_parent
        edges_df["rsa_prop"] = edges_df.apply(
            lambda row: self.bracken_rsa_lookup(nodes_df, row["child"], "rsa") / max(self.bracken_rsa_lookup(nodes_df, row["parent"], "rsa"), 1e-10),
            axis=1,
        )

        # Add node metadata and overwrite parent_tax_id with compressed lineages
        compressed_parent_map = dict(zip(edges_df["child"], edges_df["parent"]))

        nodes_df["parent_tax_id"] = nodes_df["tax_id"].map(compressed_parent_map)

        nodes_df["branches"] = nodes_df.apply(lambda row: edges_df[edges_df["parent"] == row["tax_id"]].shape[0], axis=1)

        nodes_df["parent_present"] = nodes_df["parent_tax_id"].apply(lambda x: "Yes" if pd.notna(x) else "No")

        return [nodes_df, edges_df]

    def tree_filterting_criteria(self):
        # TODO: Write different filtering criteria for trimming down the graph. This we can call it later as well.
        pass

    def add_microbial_commuity_edges(self):
        # TODO: Write a method from the feature engineering in ml scripts to account
        # for a way to connect the diverse phylum.
        # Essentially, the nodes would remain the same the taxonomy graph, but the number edges will increase
        # Currently, the phylum nodes are disconnected, each taxonomy graph exists as a separate graphs
        # Based on the inverse covariance matrix only the direct associations are connected.
        pass

    def convert_df_to_Data(self, nodes_df: pd.DataFrame, edges_df: pd.DataFrame):
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Lineage information in graph data structure.",
        usage="python3 graph_extractor.py --kraken_report <> --bracken_dir <> --output_dir <>",
    )

    parser.add_argument("--kraken_report", type=str, required=True, help="Kraken report of the sample.")

    parser.add_argument("--bracken_dir", type=str, required=True, help="Bracken directory that contains the raw bracken scores")

    parser.add_argument("--output_dir", type=str, help="Directory to save the nodes and edges dataframe for a sample.")

    args = parser.parse_args()

    # Read the kraken and bracken reports
    G = TaxGraph(args.kraken_report, args.bracken_dir, min_abd=0.0001)
    # Vertices and edges
    v, e = G.lineage_from_kraken()
    v_new, e_new = G.filter_nodes_edges_based_on_bracken_outputs(v)

    # Convert the new nodes and new edges into dataframe
    node_df, edge_df = G.convert_nodes_edges_to_df(v_new, e_new)

    # Save the dataframes in the correct directory
    node_df.to_csv(os.path.join(args.output_dir, "nodes.csv"), header=True, index=False)
    edge_df.to_csv(os.path.join(args.output_dir, "edges.csv"), header=True, index=False)

"""
python3 graph_extractor.py --kraken_report /home/chandru/lu2025-12-38/Students/chandru/assembly_testing/08_kraken2/zr23059_137/kraken_report.tsv 
        --bracken_dir /home/chandru/lu2025-12-38/Students/chandru/assembly_testing/09_bracken/zr23059_137 
        --output_dir <output directory>

"""

# kraken_report = "/home/chandru/lu2025-12-38/Students/chandru/assembly_testing/08_kraken2/zr23059_137/kraken_report.tsv"
# bracken_dir = "/home/chandru/lu2025-12-38/Students/chandru/assembly_testing/09_bracken/zr23059_137"
