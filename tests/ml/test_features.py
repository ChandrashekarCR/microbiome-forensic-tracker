"""Unit tests for ML feature engineering classes.

Tests:
    - ZeroColumnFilter
    - CLRFilter
    - MicrobiomeFeatureEngineer (network + community features)
    - GraphLaplacianFeatureEngineer (spectral / Laplacian features)
    - KBestFeatureSelection
    - LinearModelScaler
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from sklearn.exceptions import NotFittedError

from src.ml.features import (
    CLRFilter,
    GraphLaplacianFeatureEngineer,
    KBestFeatureSelection,
    LinearModelScaler,
    MicrobiomeFeatureEngineer,
    ZeroColumnFilter,
)


# ---------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------

@pytest.fixture
def sample_data():
    """A small synthetic abundance matrix with 5 samples, 6 taxa."""
    np.random.seed(42)
    X = pd.DataFrame(
        np.random.dirichlet(np.ones(6), size=5),
        columns=[f"taxon_{i}" for i in range(6)],
    )
    # Ensure some zeros to test replacement/filtering
    X.iloc[0, 1] = 0.0
    X.iloc[2, 3] = 0.0
    X.iloc[4, 5] = 0.0
    # Target lat/lon for regression
    y = pd.DataFrame(
        {"lat": np.random.uniform(55, 56, 5), "lon": np.random.uniform(12, 14, 5)}
    )
    return X, y


@pytest.fixture
def X_df(sample_data):
    return sample_data[0]


@pytest.fixture
def y_df(sample_data):
    return sample_data[1]


# ---------------------------------------------------------------------
# ZeroColumnFilter
# ---------------------------------------------------------------------

def test_zero_column_filter_fit_transform(X_df):
    # Create a copy and add a column that appears in only 1 of 5 samples
    X = X_df.copy()
    X["rare_taxon"] = 0.0
    X.iloc[0, -1] = 1.0   # only first sample has this taxon
    transformer = ZeroColumnFilter(min_prevalence=0.9, min_abd=1e-6)
    transformer.fit(X)
    assert transformer._keep_cols_ is not None
    Xt = transformer.transform(X)
    # The rare column should be dropped, so shape[1] < original shape[1]
    assert Xt.shape[1] < X.shape[1]
    assert "rare_taxon" not in Xt.columns


def test_zero_column_filter_not_fitted_raises(X_df):
    transformer = ZeroColumnFilter()
    with pytest.raises(ValueError, match="must be fitted"):
        transformer.transform(X_df)


# ---------------------------------------------------------------------
# CLRFilter
# ---------------------------------------------------------------------

def test_clr_filter_transform(X_df):
    transformer = CLRFilter(delta=1e-6)
    transformer.fit(X_df)   # does nothing but required for pipeline
    Xt = transformer.transform(X_df)
    assert isinstance(Xt, pd.DataFrame)
    assert Xt.shape == X_df.shape
    # Row sums should be near zero (CLR centered)
    row_sums = Xt.sum(axis=1)
    np.testing.assert_allclose(row_sums, 0.0, atol=1e-10)


# ---------------------------------------------------------------------
# MicrobiomeFeatureEngineer
# ---------------------------------------------------------------------

def test_microbiome_feature_engineer_fit(X_df):
    """Fit should store precision matrix and communities."""
    transformer = MicrobiomeFeatureEngineer(
        cv_folds=2,  # small for test speed
        use_edge=False,
        use_community=True,
    )
    transformer.fit(X_df)
    assert transformer.precision_matrix is not None
    assert transformer.adjacency_matrix is not None
    assert hasattr(transformer, "_communities_")
    assert hasattr(transformer, "degree_centrality")


def test_microbiome_feature_engineer_transform_without_fit_raises(X_df):
    transformer = MicrobiomeFeatureEngineer()
    with pytest.raises(AttributeError):
        transformer.transform(X_df)


def test_microbiome_feature_engineer_transform_outputs(X_df):
    """Transform should produce expected columns based on flags."""
    # Case: no extra features (only raw CLR features)
    transformer = MicrobiomeFeatureEngineer(use_edge=False, use_community=False)
    transformer.fit(X_df)
    Xt = transformer.transform(X_df)
    # Only clr_* columns
    expected_cols = [f"clr_{taxon}" for taxon in X_df.columns]
    assert set(Xt.columns) == set(expected_cols)
    assert Xt.shape[0] == X_df.shape[0]

    # Case: community features enabled
    transformer = MicrobiomeFeatureEngineer(use_edge=False, use_community=True)
    transformer.fit(X_df)
    Xt = transformer.transform(X_df)
    # Should have clr_* plus community_* columns
    clr_cols = [f"clr_{taxon}" for taxon in X_df.columns]
    comm_cols = [col for col in Xt.columns if col.startswith("community_")]
    assert len(comm_cols) > 0
    assert set(clr_cols).issubset(set(Xt.columns))

    # Case: edge features enabled (requires some edges)
    transformer = MicrobiomeFeatureEngineer(use_edge=True, use_community=False, top_k_edges=2)
    transformer.fit(X_df)
    Xt = transformer.transform(X_df)
    edge_cols = [col for col in Xt.columns if col.startswith("edge_")]
    assert len(edge_cols) > 0


def test_microbiome_feature_engineer_feature_flags_control_output(X_df):
    """Test that use_edge and use_community flags control inclusion of feature families."""
    # Without any extra features
    transformer = MicrobiomeFeatureEngineer(use_edge=False, use_community=False)
    transformer.fit(X_df)
    Xt = transformer.transform(X_df)
    assert all(col.startswith("clr_") for col in Xt.columns)

    # Only community
    transformer = MicrobiomeFeatureEngineer(use_edge=False, use_community=True)
    transformer.fit(X_df)
    Xt = transformer.transform(X_df)
    assert any(col.startswith("community_") for col in Xt.columns)
    assert not any(col.startswith("edge_") for col in Xt.columns)

    # Only edges
    transformer = MicrobiomeFeatureEngineer(use_edge=True, use_community=False, top_k_edges=2)
    transformer.fit(X_df)
    Xt = transformer.transform(X_df)
    assert any(col.startswith("edge_") for col in Xt.columns)
    assert not any(col.startswith("community_") for col in Xt.columns)

    # Both
    transformer = MicrobiomeFeatureEngineer(use_edge=True, use_community=True, top_k_edges=2)
    transformer.fit(X_df)
    Xt = transformer.transform(X_df)
    assert any(col.startswith("edge_") for col in Xt.columns)
    assert any(col.startswith("community_") for col in Xt.columns)


# ---------------------------------------------------------------------
# GraphLaplacianFeatureEngineer
# ---------------------------------------------------------------------

def test_graph_laplacian_feature_engineer_fit(X_df):
    transformer = GraphLaplacianFeatureEngineer(
        cv_folds=2,
        use_spectral=False,
        use_global_graph=False,
        use_community=False,
    )
    transformer.fit(X_df)
    assert hasattr(transformer, "laplacian_")
    assert hasattr(transformer, "spectral_basis_")


def test_graph_laplacian_feature_engineer_transform_outputs(X_df):
    # Only raw CLR features (fallback)
    transformer = GraphLaplacianFeatureEngineer(
        use_spectral=False, use_global_graph=False, use_community=False
    )
    transformer.fit(X_df)
    Xt = transformer.transform(X_df)
    # Should have clr_* only
    expected_cols = [f"clr_{taxon}" for taxon in X_df.columns]
    assert set(Xt.columns) == set(expected_cols)

    # Spectral features
    transformer = GraphLaplacianFeatureEngineer(
        use_spectral=True, use_global_graph=False, use_community=False,
        n_spectral_features=3
    )
    transformer.fit(X_df)
    Xt = transformer.transform(X_df)
    spectral_cols = [col for col in Xt.columns if col.startswith("network_spectral_")]
    assert len(spectral_cols) == 3

    # Global graph energy
    transformer = GraphLaplacianFeatureEngineer(
        use_spectral=False, use_global_graph=True, use_community=False
    )
    transformer.fit(X_df)
    Xt = transformer.transform(X_df)
    assert "network_global_laplacian_energy" in Xt.columns

    # Community Laplacian energy
    transformer = GraphLaplacianFeatureEngineer(
        use_spectral=False, use_global_graph=False, use_community=True
    )
    transformer.fit(X_df)
    Xt = transformer.transform(X_df)
    comm_cols = [col for col in Xt.columns if col.startswith("community_")]
    assert len(comm_cols) > 0


# ---------------------------------------------------------------------
# KBestFeatureSelection
# ---------------------------------------------------------------------

def test_kbest_feature_selection(X_df, y_df):
    transformer = KBestFeatureSelection(k=2)
    transformer.fit(X_df, y_df)
    assert hasattr(transformer, "selected_features")
    assert len(transformer.selected_features) == 2
    Xt = transformer.transform(X_df)
    assert Xt.shape[1] == 2
    assert set(Xt.columns) == set(transformer.selected_features)


# ---------------------------------------------------------------------
# LinearModelScaler
# ---------------------------------------------------------------------

def test_linear_model_scaler(X_df):
    scaler = LinearModelScaler()
    scaler.fit(X_df)
    Xt = scaler.transform(X_df)
    assert isinstance(Xt, pd.DataFrame)
    assert Xt.shape == X_df.shape
    # Mean should be ~0, std ~1 for each column
    np.testing.assert_allclose(Xt.mean(axis=0), 0.0, atol=1e-10)
    np.testing.assert_allclose(np.std(Xt.values, axis=0, ddof=0), 1.0, atol=1e-10)

def test_linear_model_scaler_not_fitted_raises(X_df):
    scaler = LinearModelScaler()
    with pytest.raises(ValueError, match="must be fitted"):
        scaler.transform(X_df)