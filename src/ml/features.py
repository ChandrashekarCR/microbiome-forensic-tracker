# Import libraries
import warnings

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd
from skbio.stats.composition import clr
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.covariance import GraphicalLassoCV
from sklearn.feature_selection import SelectKBest, f_regression
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore", message="invalid value encountered in subtract")


class ZeroColumnFilter(BaseEstimator, TransformerMixin):
    """
    Remove columns that are present in less than min_prevalence of samples.
    """

    def __init__(self, min_prevalence: float = 0.05, min_abd: float = 1e-6):
        self.min_prevalence = min_prevalence
        self.min_abd = min_abd
        self._keep_cols_ = None  # Private attribute

    def fit(self, X: pd.DataFrame, y: pd.Series = None):
        # Calculate prevalence
        prevalence = (X > self.min_abd).mean(axis=0)

        # Keep columns that meet the prevalence threshold
        keep_cols_ = prevalence >= self.min_prevalence
        feature_names_in_ = X.columns[keep_cols_].tolist()

        # Store the list of column names
        self._keep_cols_ = feature_names_in_

        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        if self._keep_cols_ is None:
            raise ValueError("ZeroColumnFilter must be fitted before transform")

        X_out = X.loc[:, self._keep_cols_].copy()
        X_out = X_out.loc[:, ~X_out.columns.duplicated(keep="first")]
        return X_out.astype(float)


class CLRFilter(BaseEstimator, TransformerMixin):
    """
    Centered Log-Ratio (CLR) transformation for compositional data.

    Steps:
        1. Multiplicative replacement of zeros (impute with delta)
        2. Row-wise normalization to relative abundance (sum = 1)
        3. CLR: log(x) - mean(log(x)) for each sample

    This is a standalone transformer that can be used in an sklearn Pipeline.
    """

    def __init__(self, delta: float = 1e-6):
        """
        Parameters
        ----------
        delta : float, default=1e-6
            Small pseudo-count to replace zeros before log transformation.
        """
        self.delta = delta

    def fit(self, X, y=None):
        """
        Fit method - does nothing (CLR is parameter-free).
        Required for sklearn pipeline compatibility.
        """
        return self

    def transform(self, X) -> pd.DataFrame:
        """
        Apply CLR transformation to the input data.

        Parameters
        ----------
        X : pd.DataFrame or np.ndarray
            Relative abundance data (features as columns, samples as rows).
            Can contain zeros - they will be handled.

        Returns
        -------
        pd.DataFrame or np.ndarray
            CLR-transformed data (same shape as input).
        """
        # Preserve index/columns if input is DataFrame
        is_df = isinstance(X, pd.DataFrame)
        if is_df:
            index = X.index
            columns = X.columns
            X = X.values
        else:
            X = np.asarray(X, dtype=float)

        # Step 1: Multiplicative replacement (handle zeros)
        X[X == 0] = self.delta

        # Step 2: Row normalization (ensure compositional)
        row_sums = X.sum(axis=1, keepdims=True)
        # Safety check: if any row sums to 0 (shouldn't happen after replacement)
        row_sums[row_sums == 0] = self.delta
        X = X / row_sums

        # Step 3: Clipping to avoid log(0) or log(negative)
        X = np.clip(X, self.delta, 1.0)

        # Step 4: Centered Log-Ratio transformation
        clr_transformed = clr(X)

        # Step 5: Return in same format as input
        if is_df:
            return pd.DataFrame(clr_transformed, index=index, columns=columns)
        return clr_transformed


class MicrobiomeFeatureEngineer(BaseEstimator, TransformerMixin):
    """
    Feature Engineering: CLR + ecological network summaries + diversity
    Fit the GraphicalLasso only to the training data.
    """

    def __init__(
        self,
        cv_folds: int = 5,
        max_iter: int = 2000,
        n_jobs: int = -1,
        top_k_edges: int = 20,
        use_edge: bool = False,
        use_community: bool = True,
        min_community_size: int = 3,
    ):

        self.cv_folds = cv_folds
        self.max_iter = max_iter
        self.n_jobs = n_jobs
        self.top_k_edges = top_k_edges
        self.glasso = GraphicalLassoCV(cv=self.cv_folds, n_jobs=self.n_jobs, max_iter=self.max_iter)
        self.precision_matrix = None  # Sparse Inverse Covariance matrix
        self.adjacency_matrix = None  # Binary graph matrix 1 denotes edge between two taxa and 0 is no edge
        self.use_edge = use_edge
        self.use_community = use_community
        self.min_community_size = min_community_size

    def get_top_edges_by_absolute_weight(self, precision_matrix, taxa_names, top_k=20):
        """
        Get top K edges by absolute weight (captures both positive and negative interactions).
        """
        # Get all edges (upper triangular, excluding diagonal)
        rows, cols = np.triu_indices_from(precision_matrix, k=1)
        edge_weights = precision_matrix[rows, cols]

        # Get indices sorted by absolute value (descending)
        sorted_indices = np.argsort(np.abs(edge_weights))[::-1]  # Descending

        # Take top K
        top_k_indices = sorted_indices[:top_k]

        # Extract edge information
        top_edges = []
        for idx in top_k_indices:
            u, v = rows[idx], cols[idx]
            weight = edge_weights[idx]
            top_edges.append(
                {
                    "taxon_u": taxa_names[u],
                    "taxon_v": taxa_names[v],
                    "weight": weight,
                    "abs_weight": np.abs(weight),
                    "interaction_type": "positive" if weight > 0 else "negative",
                }
            )

        return top_edges

    def fit(self, X: pd.DataFrame, y: pd.Series = None):
        """
        Learn the ecological network from the training data only
        """
        self.taxa_names_ = X.columns.to_list()
        X_raw = X.values.copy()

        # CLR (Centered Log Ratio) Transformation to handle compositional data from sequencing
        self.X_clr_train_ = X_raw

        # Check for NaN or Inf
        if np.any(~np.isfinite(self.X_clr_train_)):
            print("Warning: NaN/Inf detected in CLR data. Replacing with 0.")
            self.X_clr_train_ = np.nan_to_num(self.X_clr_train_, nan=0.0, posinf=0.0, neginf=0.0)

        # Fit sparse inverse covariance
        # This solves the L1 penalized mathematical optimization
        print("Obtaining sparse inverse covariance matrix")
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

        G = nx.Graph()
        G.add_nodes_from(range(len(self.taxa_names_)))
        rows, cols = np.where(np.triu(self.adjacency_matrix, k=1) == 1)
        for r, c in zip(rows, cols):
            G.add_edge(int(r), int(c), weight=float(abs(self.precision_matrix[r, c])))

        raw_communities = nx.community.louvain_communities(G, weight="weight", seed=42)

        self._communities_ = [
            {"community_id": i, "taxa": [self.taxa_names_[idx] for idx in sorted(comm)]}
            for i, comm in enumerate(raw_communities)
            if len(comm) >= self.min_community_size
        ]

        # Extract network derived features per taxon
        Gd = nx.from_numpy_array(self.adjacency_matrix)
        self.degree_centrality = nx.degree_centrality(Gd)
        self.betweenness = nx.betweenness_centrality(Gd)

        return self

    def transform(self, X: pd.DataFrame):
        """
        Apply learned transformation to any data (train,val or test)
        """
        X_raw = X.values.copy()
        # X_nonzero = self.multiplicative_replacement(X_raw)
        # X_clr_data = clr(X_nonzero)
        X_clr_data = X_raw

        if np.any(~np.isfinite(X_clr_data)):
            X_clr_data = np.nan_to_num(X_clr_data, nan=0.0, posinf=0.0, neginf=0.0)

        features = {}

        # a) Raw CLR features
        for i, taxon in enumerate(self.taxa_names_):
            features[f"clr_{taxon}"] = X_clr_data[:, i]

        # b) Community aggregated scores
        if self.use_community:
            col_index = {name: i for i, name in enumerate(self.taxa_names_)}
            for comm in self._communities_:
                idx = [col_index[t] for t in comm["taxa"] if t in col_index]
                if len(idx) < self.min_community_size:
                    continue
                features[f"community_{comm['community_id']}_score"] = X_clr_data[:, idx].sum(axis=1)

        # c) Extract specific Sample-by-Edge active interactions
        # We find all non-zero edges in the global network
        if self.use_edge:
            top_edges = self.get_top_edges_by_absolute_weight(self.precision_matrix, self.taxa_names_, self.top_k_edges)

            for edge in top_edges:
                u = self.taxa_names_.index(edge["taxon_u"])
                v = self.taxa_names_.index(edge["taxon_v"])
                edge_name = f"edge_{edge['taxon_u']}_AND_{edge['taxon_v']}"

                # The active strength of this edge in each sample:
                # global_weight * abundance_u * abundance_v
                global_weight = self.precision_matrix[u, v]
                edge_activations = global_weight * X_clr_data[:, u] * X_clr_data[:, v]
                features[edge_name] = edge_activations

        return pd.DataFrame(features, index=X.index)

    def plot_network(self, output_file: str = "microbiome_network.png"):

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


# Helper function for computing f_regression scores for multi-ouput targets.
def multioutput_f_regression(X, y):
    """
    Computes f_regression scores for multi-output targets by averaging the
    F-statistics obtained for each target independently.
    """
    # If y is 1D, fall back to standard f_regression
    if len(y.shape) == 1 or y.shape[1] == 1:
        return f_regression(X, y)

    # Calculate scores for each column in y
    scores_per_target = []
    p_values_per_target = []

    for i in range(y.shape[1]):
        score, pval = f_regression(X, y[:, i] if isinstance(y, np.ndarray) else y.iloc[:, i])
        scores_per_target.append(score)
        p_values_per_target.append(pval)

    # Average the scores across targets to pick features globally relevant to both lat/long
    avg_scores = np.mean(scores_per_target, axis=0)
    avg_pvals = np.mean(p_values_per_target, axis=0)

    return avg_scores, avg_pvals


class KBestFeatureSelection(BaseEstimator, TransformerMixin):
    def __init__(self, score_func=multioutput_f_regression, k: int = 3):
        self.score_func = score_func
        self.k = k

    def fit(self, X: pd.DataFrame, y: pd.DataFrame = None):

        # 1. Initialize the internal scikit-learn selector
        self.selector_ = SelectKBest(score_func=self.score_func, k=self.k)

        # 2. Fit the selector to find the best features
        self.selector_.fit(X, y)

        # 3. Cache selected features names if input is a Dataframe
        if isinstance(X, pd.DataFrame):
            mask = self.selector_.get_support()
            self.selected_features = X.columns[mask].tolist()

        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:

        # 4. Rduce the dataset to selected features
        X_transformed = self.selector_.transform(X)

        # 5. Reconstructu Dataframe with correct column names and row indices
        if isinstance(X, pd.DataFrame):
            return pd.DataFrame(X_transformed, columns=self.selected_features)

        return X_transformed


class LinearModelScaler(BaseEstimator, TransformerMixin):
    def __init__(self):
        self.scaler = None
        self.feature_names_in_ = None
        self.n_features_in_ = None

    def fit(self, X: pd.DataFrame, y: pd.Series = None):
        # Store feature names
        if isinstance(X, pd.DataFrame):
            self.feature_names_in_ = X.columns.tolist()
            self.n_features_in_ = X.shape[1]

        # Create and fit the scaler
        self.scaler = StandardScaler()
        self.scaler.fit(X)

        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        if self.scaler is None:
            raise ValueError("LinearModelScaler must be fitted before transform")

        # Transform
        X_scaled = self.scaler.transform(X)

        # Return as DataFrame with same index and columns
        if isinstance(X, pd.DataFrame):
            return pd.DataFrame(X_scaled, index=X.index, columns=X.columns)

        return X_scaled


class GraphLaplacianFeatureEngineer(BaseEstimator, TransformerMixin):
    """
    Network-only feature engineering from a sparse inverse covariance network.

    Input
    -----
    X : CLR-transformed species matrix, samples x species.

    Output
    ------
    Network-derived sample features only:
      1. Graph Fourier / spectral coordinates
      2. Global graph smoothness
      3. Community-specific Laplacian coherence scores

    """

    def __init__(
        self,
        cv_folds: int = 5,
        max_iter: int = 2000,
        n_jobs: int = -1,
        n_spectral_features: int = 8,
        min_community_size: int = 3,
        edge_threshold: float = 1e-5,
        eps: float = 1e-12,
        use_spectral: bool = False,
        use_global_graph: bool = False,
        use_community: bool = False,
    ):
        self.cv_folds = cv_folds
        self.max_iter = max_iter
        self.n_jobs = n_jobs
        self.n_spectral_features = n_spectral_features
        self.min_community_size = min_community_size
        self.edge_threshold = edge_threshold
        self.eps = eps
        self.use_spectral = use_spectral
        self.use_global_graph = use_global_graph
        self.use_community = use_community

    def fit(self, X: pd.DataFrame, y=None):
        """
        Fit ONLY on a training fold.
        X must already be CLR-transformed.
        """
        self.taxa_names_ = list(X.columns)

        x_train = X.to_numpy(dtype=float, copy=True)
        x_train = np.nan_to_num(
            x_train,
            nan=0.0,
            posinf=0.0,
            neginf=0.0,
        )

        # 1. Fit sparse inverse covariance network.
        self.glasso_ = GraphicalLassoCV(
            cv=self.cv_folds,
            n_jobs=self.n_jobs,
            max_iter=self.max_iter,
        )
        self.graph_failed_ = False
        try:
            self.glasso_.fit(x_train)
            self.precision_matrix_ = self.glasso_.precision_
        except (FloatingPointError, np.linalg.LinAlgError, ValueError) as exc:
            # Stage 4 can hit a near-singular covariance on some folds.
            # Fall back to a safe, zero-interaction graph so the search continues.
            print(f"Warning: GraphicalLassoCV failed ({exc}). Falling back to empty network features for this fold.")
            self.graph_failed_ = True
            self.precision_matrix_ = np.zeros((x_train.shape[1], x_train.shape[1]), dtype=float)
            self.affinity_matrix_ = np.zeros_like(self.precision_matrix_)
            self.laplacian_ = np.eye(x_train.shape[1], dtype=float)
            self.spectral_basis_ = np.zeros((x_train.shape[1], 0), dtype=float)
            self.spectral_eigenvalues_ = np.array([], dtype=float)
            self.community_indices_ = []
            self.partial_corr_ = np.zeros_like(self.precision_matrix_)
            self.degree_centrality = dict.fromkeys(range(x_train.shape[1]), 0.0)
            self.betweenness = dict.fromkeys(range(x_train.shape[1]), 0.0)
            return self

        self.affinity_matrix_ = np.abs(self.precision_matrix_)
        self.partial_corr_ = self.precision_matrix_

        # 2. Convert precision matrix to partial correlations.
        diagonal = np.sqrt(
            np.outer(
                np.diag(self.precision_matrix_),
                np.diag(self.precision_matrix_),
            )
        )

        partial_corr = -self.precision_matrix_ / np.maximum(
            diagonal,
            self.eps,
        )
        np.fill_diagonal(partial_corr, 0.0)

        self.partial_corr_ = partial_corr

        # Use absolute partial correlations as weighted graph affinities.
        affinity = np.abs(partial_corr)
        affinity[affinity < self.edge_threshold] = 0.0
        np.fill_diagonal(affinity, 0.0)

        self.affinity_matrix_ = affinity

        # 3. Build normalized graph Laplacian.
        degree = affinity.sum(axis=1)
        degree_inv_sqrt = np.zeros_like(degree)

        valid_degree = degree > self.eps
        degree_inv_sqrt[valid_degree] = 1.0 / np.sqrt(degree[valid_degree])

        d_inv_sqrt = np.diag(degree_inv_sqrt)

        self.laplacian_ = np.eye(affinity.shape[0]) - d_inv_sqrt @ affinity @ d_inv_sqrt

        # 4. Graph spectral basis.
        eigenvalues, eigenvectors = np.linalg.eigh(self.laplacian_)

        # Ignore near-zero eigenvectors associated with connected components.
        usable = np.where(eigenvalues > 1e-8)[0]

        n_keep = min(self.n_spectral_features, len(usable))

        if n_keep == 0:
            # Safe fallback for a graph with no usable edges.
            self.spectral_basis_ = np.zeros((affinity.shape[0], 0))
        else:
            self.spectral_basis_ = eigenvectors[:, usable[:n_keep]]

        self.spectral_eigenvalues_ = eigenvalues[usable[:n_keep]]

        # 5. Louvain communities from the weighted network.
        graph = nx.from_numpy_array(affinity)

        raw_communities = nx.community.louvain_communities(
            graph,
            weight="weight",
            seed=42,
        )

        self.community_indices_ = [
            np.array(sorted(list(community)), dtype=int) for community in raw_communities if len(community) >= self.min_community_size
        ]

        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """
        Generate network-only features for train, validation, or test data.
        """
        X = X.loc[:, self.taxa_names_]

        x_clr = X.to_numpy(dtype=float, copy=True)
        x_clr = np.nan_to_num(
            x_clr,
            nan=0.0,
            posinf=0.0,
            neginf=0.0,
        )

        features = {}

        # As a fallback we add the raw CLR features as well
        for i, taxon in enumerate(self.taxa_names_):
            features[f"clr_{taxon}"] = x_clr[:, i]

        # A. Network spectral coordinates:
        # Each coordinate is a graph-informed projection of the full species profile.
        if self.use_spectral:
            if self.spectral_basis_.shape[1] > 0:
                spectral_scores = x_clr @ self.spectral_basis_

                for component_index in range(spectral_scores.shape[1]):
                    features[f"network_spectral_{component_index + 1}"] = spectral_scores[:, component_index]

        # B. Global graph Laplacian energy:
        # High value: connected taxa have strongly discordant CLR behavior.
        # Low value: connected taxa have coherent CLR behavior.
        if self.use_global_graph:
            global_energy = np.sum(
                x_clr * (x_clr @ self.laplacian_),
                axis=1,
            )

            clr_norm = np.sum(np.square(x_clr), axis=1)

            features["network_global_laplacian_energy"] = global_energy / (clr_norm + self.eps)

        # C. Community-specific network coherence:
        # One topology-aware score per detected microbial community.
        if self.use_community:
            for community_id, idx in enumerate(self.community_indices_):
                x_community = x_clr[:, idx]
                L_community = self.laplacian_[np.ix_(idx, idx)]

                community_energy = np.sum(
                    x_community * (x_community @ L_community),
                    axis=1,
                )

                community_norm = np.sum(
                    np.square(x_community),
                    axis=1,
                )

                features[f"community_{community_id}_laplacian_energy"] = community_energy / (community_norm + self.eps)

        return pd.DataFrame(features, index=X.index)
