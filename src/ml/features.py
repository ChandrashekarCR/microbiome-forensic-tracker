# Import libraries
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd
from skbio.stats.composition import clr
from sklearn.covariance import GraphicalLassoCV
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.pipeline import Pipeline

from ml.data_loading import DatabaseRSA, db_reader

class ZeroColumnFilter(BaseEstimator,TransformerMixin):
    """
    Remove columns that are all zeros (fit on train only).
    """
    def __init__(self, min_prevalence: float=0.05):
        self.min_prevalence = min_prevalence
    
    def fit(self, X: pd.DataFrame, y: pd.Series=None):
        X = X.astype(float)
        X = X.loc[:, (X != 0 ).any(axis=0)]
        self.keep_cols_ = X[X >= self.min_prevalence].columns.tolist()
        return self
    
    def transform(self,X: pd.DataFrame) -> pd.DataFrame:
        return X.loc[:,self.keep_cols_].copy()

class MicrobiomeFeatureEngineer(BaseEstimator,TransformerMixin):
    """
    Feature Engineering: CLR + ecological network summaries + diversity
    Fit the GraphicalLasso only to the training data.
    """
    def __init__(self,cv_folds: int=5, max_iter:int=2000, n_jobs: int=-1, top_k_edges:int=20):
        self.top_k_edges = top_k_edges
        self.glasso = GraphicalLassoCV(cv=cv_folds, n_jobs=n_jobs, max_iter=max_iter)
        self.precision_matrix = None # Sparse Inverse Covariance matrix
        self.adjacency_matrix = None # Binary graph matrix 1 denotes edge between two taxa and 0 is no edge
        self.keystone_taxa_ = []

    def multiplicative_replacement(self, X: np.ndarray, delta: float =1e-6) -> pd.DataFrame:
        """
        CLR log transformation requires non zeros values hen hadded a small 0 value which is negligible
        """
        X = np.array(X, dtype=float)
        X[X == 0] = delta
        X /= X.sum(axis=1, keepdims=True)
        return X
    
    def fit(self, X:pd.DataFrame,y: pd.Series=None):
        """
        Learn the ecological network from the training data only
        """
        self.taxa_names_ = X.columns.to_list()
        X_raw = X.values.copy()

        # CLR (Centered Log Ratio) Transforamtion to handle decompositions while sequencing
        X_nonzero = self.multiplicative_replacement(X_raw)
        self.X_clr_train_ = clr(X_nonzero)

        # Fit sparse inverse covariance
        # This solves the L1 penalized mathematical optimization
        print("Obtaining sprase inverse covariance matrix")
        self.glasso.fit(self.X_clr_train_)

        # Extract the precision matrix (Theta)
        best_lambda = self.glasso.alpha_
        print(f"Best lambda (alpha) selected by cv: {best_lambda}")
        # Sparse inverse covariance
        self.precision_matrix = self.glasso.precision_ 

        # Build the ecological network
        # Convert to Adjacency Matrix (Boolean Network)
        # Any value sufficiently far from 0 is an edge
        self.adjacency_matrix = (np.abs(self.precision_matrix) > 1e-5).astype(int)
        np.fill_diagonal(self.adjacency_matrix, 0)
        G = nx.from_numpy_array(self.adjacency_matrix)

        # Extract network derived features per taxon
        self.degree_centrality = nx.degree_centrality(G)
        self.betweenness = nx.betweenness_centrality(G)

        return self
    
    def transform(self, X:pd.DataFrame):
        """
        Apply learned transformation to any data (train,val or test)
        """
        X_raw = X.values.copy()
        X_nonzero = self.multiplicative_replacement(X_raw)
        X_clr_data = clr(X_nonzero)

        features = {}
        n_samples = X_clr_data.shape[0]

        # a) Raw CLR features
        for i,taxon in enumerate(self.taxa_names_):
            features[f"clr_{taxon}"] = X_clr_data[:, i]

        # b) Degree-weighted abundances (amplify ecologically connected taxa)
        for i, taxon in enumerate(self.taxa_names_):
            deg = self.degree_centrality.get(i, 0)
            features[f"deg_weighted_{taxon}"] = X_clr_data[:, i] * deg

        # c) Hub scores (betweenness-weighted)
        for i, taxon in enumerate(self.taxa_names_):
            btw = self.betweenness.get(i, 0)
            features[f"hub_weighted_{taxon}"] = X_clr_data[:, i] * btw

        # d) Network summary statistics per sample
        # Interaction strength: sum of precision matrix edges weighted by abundance
        for i in range(n_samples):
            sample_vec = X_clr_data[i, :]
            # Quadratic form captures pairwise ecological interactions
            features.setdefault("ecological_interaction", []).append(sample_vec @ self.precision_matrix @ sample_vec)

        # e) Extract specific Sample-by-Edge active interactions
        # We find all non-zero edges in the global network
        edges = np.argwhere(np.triu(self.adjacency_matrix, k=1) > 0)

        for u, v in edges:
            taxon_u = self.taxa_names_[u]
            taxon_v = self.taxa_names_[v]
            edge_name = f"edge_{taxon_u}_AND_{taxon_v}"

            # The active strength of this edge in each sample:
            # global_weight * abundance_u * abundance_v
            global_weight = self.precision_matrix[u, v]
            edge_activations = global_weight * X_clr_data[:, u] * X_clr_data[:, v]

            features[edge_name] = edge_activations
        
        return pd.DataFrame(features,index=X.index)
    
    def plot_network(self, output_file: str="microbiome_network.png"):

        # Build the graph
        G = nx.from_numpy_array(self.adjacency_matrix)

        # Relabel nodes from array indices (0, 1, 2) to biological names (Taxa 1, Taxa 2)
        mapping = dict(enumerate(self.taxa_names_))
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


