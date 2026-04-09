# Import libraries
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd
from skbio.stats.composition import clr
from sklearn.covariance import GraphicalLassoCV

from ml.data_loading import DatabaseRSA, db_reader


class MicrobiomeNetworkFeatures:
    def __init__(self, X_abundance: pd.DataFrame, cv_folds: int = 5):
        self.X_abundance = X_abundance
        # Pre-preocessing for computational efficeincy
        # Remove all-zero columns (taxa)
        self.X_abundance = self.X_abundance.loc[:, (self.X_abundance != 0).any(axis=0)]
        # Remove all-zero rows (samples)
        self.X_abundance = self.X_abundance[(self.X_abundance != 0).any(axis=1)]

        self.glasso = GraphicalLassoCV(cv=cv_folds, n_jobs=-1, max_iter=500)
        self.precision_matrix = None
        self.adjacency_matrix = None
        self.keystone_taxa_ = []

    def multiplicative_replacement(self, X, delta=1e-6) -> pd.DataFrame:
        X = np.array(X, dtype=float)
        X[X == 0] = delta
        X /= X.sum(axis=1, keepdims=True)
        return X

    def fit(self) -> pd.DataFrame:
        """
        self.X_abundance: pandas Dataframe where rows are samples and
        columns are Taxa (Species). The values are relative abundances
        """

        # First we need to handle 0 values. We will replace 0s with a
        # small delta while maintaing the compositional sum.
        X_nonzero = self.multiplicative_replacement(self.X_abundance.values)

        # To handle the compostion problem we will use centered log ratio
        X_clr = clr(X_nonzero)

        # Fit sparse inverse covariance
        # This solves the L1 penalized mathematical optimization
        print("Obtaining sprase inverse covariance matrix")
        self.glasso.fit(X_clr)

        # Extract the precision matrix (Theta)
        self.precision_matrix = self.glasso.precision_  # Sparse inverse covariance
        # covariance_matrix = self.glasso.covariance_ # Covaraince matrix

        # Build the ecological metwork
        # Convert to Adjacency Matrix (Boolean Network)
        # Any value sufficiently far from 0 is an edge
        self.adjacency_matrix = (np.abs(self.precision_matrix) > 1e-5).astype(int)
        np.fill_diagonal(self.adjacency_matrix, 0)
        G = nx.from_numpy_array(self.adjacency_matrix)

        # Extract network derived features per taxon
        degree_centrality = nx.degree_centrality(G)
        betweenness = nx.betweenness_centrality(G)

        # Build augmented feature matrix
        n_taxa = X_clr.shape[1]

        # Per-sample features: CLR abundances + network-weighted abundances
        network_features = {}

        # a) Raw CLR features
        for i in range(n_taxa):
            taxon = self.X_abundance.columns[i]
            network_features[f"clr_{taxon}"] = X_clr[:, i]

        # b) Degree-weighted abundances (amplify ecologically connected taxa)
        for i in range(n_taxa):
            taxon = self.X_abundance.columns[i]
            deg = degree_centrality.get(i, 0)
            network_features[f"deg_weighted_{taxon}"] = X_clr[:, i] * deg

        # c) Hub scores (betweenness-weighted)
        for i in range(n_taxa):
            taxon = self.X_abundance.columns[i]
            btw = betweenness.get(i, 0)
            network_features[f"hub_weighted_{taxon}"] = X_clr[:, i] * btw

        # d) Network summary statistics per sample
        # Interaction strength: sum of precision matrix edges weighted by abundance
        for i in range(X_clr.shape[0]):
            sample_vec = X_clr[i, :]
            # Quadratic form captures pairwise ecological interactions
            network_features.setdefault("ecological_interaction_score", []).append(sample_vec @ self.precision_matrix @ sample_vec)

        # e) Extract specific Sample-by-Edge active interactions
        # We find all non-zero edges in the global network
        edges = np.argwhere(np.triu(self.adjacency_matrix, k=1) > 0)

        for u, v in edges:
            taxon_u = self.X_abundance.columns[u]
            taxon_v = self.X_abundance.columns[v]
            edge_name = f"edge_{taxon_u}_AND_{taxon_v}"

            # The active strength of this edge in each sample:
            # global_weight * abundance_u * abundance_v
            global_weight = self.precision_matrix[u, v]
            edge_activations = global_weight * X_clr[:, u] * X_clr[:, v]

            network_features[edge_name] = edge_activations

        self.extracted_features_ = pd.DataFrame(network_features, index=self.X_abundance.index)
        return self.extracted_features_

        # return pd.DataFrame(network_features, index=self.X_abundance.index)

    def plot_network(self, output_file="microbiome_network.png"):

        # Taxa names
        taxa_names = self.X_abundance.columns

        # Build the graph
        G = nx.from_numpy_array(self.adjacency_matrix)

        # Relabel nodes from array indices (0, 1, 2) to biological names (Taxa 1, Taxa 2)
        mapping = dict(enumerate(taxa_names))
        G = nx.relabel_nodes(G, mapping)

        # Network visualization gets messy if we plot everything.
        # Let's remove isolated microbes (Degree = 0) that have no edges
        isolated_nodes = list(nx.isolates(G))
        G.remove_nodes_from(isolated_nodes)

        if len(G.nodes) == 0:
            print("No significant ecological interactions found (all margins were 0).")
            return

        plt.figure(figsize=(15, 15))

        # Layout algorithm for organic clustering
        pos = nx.spring_layout(G, k=0.15, seed=42)

        # Node sizes proportional to the number of ecological connections
        degrees = dict(G.degree())
        node_sizes = [v * 50 + 50 for v in degrees.values()]

        # Draw Network
        nx.draw_networkx_nodes(G, pos, node_size=node_sizes, node_color="skyblue", alpha=0.8)
        nx.draw_networkx_edges(G, pos, alpha=0.4, edge_color="gray")
        nx.draw_networkx_labels(G, pos, font_size=8, font_color="black")

        plt.title("Ecological Interaction Network (Graphical Lasso)", fontsize=16)
        plt.axis("off")
        plt.tight_layout()
        plt.savefig(output_file, dpi=300)
        plt.close()
        print(f"Network visualization saved successfully to {output_file}")


samples = db_reader.DatabaseCreate(db="../../databases/malmo.db")
rsa = DatabaseRSA(db="../../databases/malmo.db", db_table="malmo_order")
df = rsa.merge_data(samples.get_samples(), rsa.sql_to_clean())

X = df.drop(["sample_id", "latitude", "longitude", "zone"], axis=1)

engineer = MicrobiomeNetworkFeatures(X)
features = engineer.fit()
print(features)
engineer.plot_network(output_file="microbiome_network.png")
