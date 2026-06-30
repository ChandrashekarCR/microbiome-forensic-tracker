import numpy as np
import pandas as pd
import pytest

from src.ml.features import MicrobiomeFeatureEngineer, ZeroColumnFilter


@pytest.mark.parametrize(
    "min_prevalence, min_abd, X, expected_cols",
    [
        # Case 1: very low prevalence threshold, only column c is frequent enough
        (
            0.05,
            1e-6,
            pd.DataFrame(
                {
                    "a": [0, 0, 0, 0],  # prevalence 0.0
                    "b": [1, 0, 0, 0],  # prevalence 0.25
                    "c": [1, 1, 1, 1],  # prevalence 1.0
                }
            ),
            ["b", "c"],  # if min_prevalence == 0.05, b (0.25) and c (1.0) are kept
        ),
        # Case 2: threshold 0.25, all three columns meet it
        (
            0.25,
            1e-6,
            pd.DataFrame(
                {
                    "a": [0, 0, 1, 0],  # prevalence 0.25
                    "b": [1, 0, 0, 0],  # prevalence 0.25
                    "c": [1, 1, 1, 1],  # prevalence 1.0
                }
            ),
            ["a", "b", "c"],
        ),
        # Case 3: threshold 0.5, only c is kept
        (
            0.5,
            1e-6,
            pd.DataFrame(
                {
                    "a": [0, 0, 1, 0],  # prevalence 0.25
                    "b": [1, 0, 0, 0],  # prevalence 0.25
                    "c": [1, 1, 1, 1],  # prevalence 1.0
                }
            ),
            ["c"],
        ),
    ],
)
def test_zero_column_filter(min_prevalence, min_abd, X, expected_cols):
    filt = ZeroColumnFilter(min_prevalence=min_prevalence, min_abd=min_abd)
    filt.fit(X)

    # The transformer stores kept columns in _keep_cols_
    assert filt._keep_cols_ == expected_cols

    Xt = filt.transform(X)
    assert list(Xt.columns) == expected_cols
    assert all(str(dtype) == "float64" for dtype in Xt.dtypes)


@pytest.fixture
def small_microbiome_df():
    """
    Fixture: small synthetic microbiome abundance table.

    - 5 samples (rows)
    - 4 taxa (columns)
    - Contains zeros and non-zero values to exercise multiplicative_replacement and CLR.

    This keeps tests fast and deterministic while resembling real compositional data.
    """
    data = {
        "taxon_A": [0.1, 0.0, 0.3, 0.0, 0.2],
        "taxon_B": [0.0, 0.2, 0.1, 0.0, 0.3],
        "taxon_C": [0.4, 0.3, 0.0, 0.1, 0.0],
        "taxon_D": [0.5, 0.5, 0.6, 0.9, 0.5],
    }
    return pd.DataFrame(data, index=[f"sample_{i}" for i in range(5)])


@pytest.fixture
def base_transformer():
    """
    Fixture: MicrobiomeFeatureEngineer with all feature types enabled.

    - use_clr: raw CLR features
    - use_degree: degree-weighted features
    - use_hub: betweenness-weighted features
    - use_edge: edge-based interaction features

    Using small cv_folds keeps GraphicalLassoCV fast for tests.
    """
    return MicrobiomeFeatureEngineer(
        cv_folds=3,  # fewer folds for speed
        max_iter=500,  # lower iteration count for tests
        n_jobs=1,  # predictable single-threaded behaviour
        top_k_edges=5,  # small number of edges
        use_clr=True,
        use_degree=True,
        use_hub=True,
        use_edge=True,
    )


def test_fit_learns_network_and_clr(small_microbiome_df, base_transformer):
    """
    Test that .fit():

    - Stores taxa_names_ matching input columns.
    - Computes CLR-transformed training data (X_clr_train_) with same shape as input.
    - Fits GraphicalLassoCV and produces a precision_matrix and adjacency_matrix.
    - Ensures no NaN or Inf values remain in X_clr_train_.

    This validates that the core learning step is numerically stable and
    that network-related attributes are initialized properly.
    """
    X = small_microbiome_df

    transformer = base_transformer
    transformer.fit(X)

    # Taxa names preserved
    assert transformer.taxa_names_ == list(X.columns)

    # CLR data shape matches (n_samples, n_taxa)
    assert transformer.X_clr_train_.shape == X.shape
    assert np.all(np.isfinite(transformer.X_clr_train_))

    # Precision and adjacency matrices exist with correct square shape
    n_taxa = X.shape[1]
    assert transformer.precision_matrix.shape == (n_taxa, n_taxa)
    assert transformer.adjacency_matrix.shape == (n_taxa, n_taxa)

    # Diagonal of adjacency should be zero as set in fit()
    assert np.all(np.diag(transformer.adjacency_matrix) == 0)

    # Degree and betweenness centrality dictionaries should have one entry per taxon index
    assert len(transformer.degree_centrality) == n_taxa
    assert len(transformer.betweenness) == n_taxa


def test_transform_outputs_features_with_expected_shape_and_names(small_microbiome_df, base_transformer):
    """
    Test that .transform():

    - Accepts a new DataFrame with the same taxa columns.
    - Returns a feature DataFrame with:
        * index identical to input
        * only numeric values (no NaNs/Infs)
        * columns matching the enabled feature families:
            clr_*, deg_weighted_*, hub_weighted_*, edge_*

    This ensures that the transformer can be used safely in pipelines for
    train/validation/test splits without breaking on unseen samples.
    """
    X = small_microbiome_df

    transformer = base_transformer
    transformer.fit(X)

    X_trans = transformer.transform(X)

    # Index preserved
    assert list(X_trans.index) == list(X.index)

    # All values finite
    assert np.all(np.isfinite(X_trans.to_numpy()))

    # Expected CLR feature columns present
    clr_cols = [c for c in X_trans.columns if c.startswith("clr_")]
    assert len(clr_cols) == X.shape[1]  # one CLR feature per taxon

    # Degree-weighted feature columns present
    deg_cols = [c for c in X_trans.columns if c.startswith("deg_weighted_")]
    assert len(deg_cols) == X.shape[1]

    # Hub-weighted feature columns present
    hub_cols = [c for c in X_trans.columns if c.startswith("hub_weighted_")]
    assert len(hub_cols) == X.shape[1]

    # Edge-based interaction features present (top_k_edges)
    edge_cols = [c for c in X_trans.columns if c.startswith("edge_")]
    assert len(edge_cols) == transformer.top_k_edges


@pytest.mark.parametrize(
    "use_clr, use_degree, use_hub, use_edge",
    [
        (True, False, False, False),
        (False, True, False, False),
        (False, False, True, False),
        (False, False, False, True),
        (True, True, True, True),
    ],
)
def test_feature_family_flags_control_output(small_microbiome_df, use_clr, use_degree, use_hub, use_edge):
    """
    Test that the boolean flags in __init__ correctly control which feature
    families are present in the transformed DataFrame.

    This is important so that downstream experiments can enable/disable
    CLR, degree, hub, and edge features independently without code changes.
    """
    X = small_microbiome_df
    transformer = MicrobiomeFeatureEngineer(
        cv_folds=3,
        max_iter=300,
        n_jobs=1,
        top_k_edges=3,
        use_clr=use_clr,
        use_degree=use_degree,
        use_hub=use_hub,
        use_edge=use_edge,
    )
    transformer.fit(X)
    X_trans = transformer.transform(X)

    cols = list(X_trans.columns)

    # Check each family according to flags
    has_clr = any(c.startswith("clr_") for c in cols)
    has_deg = any(c.startswith("deg_weighted_") for c in cols)
    has_hub = any(c.startswith("hub_weighted_") for c in cols)
    has_edge = any(c.startswith("edge_") for c in cols)

    assert has_clr == use_clr
    assert has_deg == use_degree
    assert has_hub == use_hub
    assert has_edge == use_edge


def test_multiplicative_replacement_handles_zeros_and_row_sums(small_microbiome_df, base_transformer):
    """
    Test multiplicative_replacement:

    - Replaces zeros with a small delta and normalizes rows to relative abundances.
    - Returns an array with the same shape as input.
    - Ensures all entries are strictly positive and <= 1 (after clipping),
      so that CLR log-transform will not encounter log(0) or negative values.

    This protects the CLR step from numerical issues when microbiome data
    contains many zeros or low-abundance taxa.
    """
    X = small_microbiome_df.values
    transformer = base_transformer

    X_repl = transformer.multiplicative_replacement(X, delta=1e-6)

    assert X_repl.shape == X.shape

    # All values in (0, 1]
    assert np.all(X_repl > 0.0)
    assert np.all(X_repl <= 1.0)

    # Row sums approximately 1 (relative abundances)
    row_sums = X_repl.sum(axis=1)
    assert np.allclose(row_sums, 1.0, atol=1e-6)
