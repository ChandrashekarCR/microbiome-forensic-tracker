"""
Unit tests for `backend/predict.py`.

We don't want to load the real ~MB sklearn pickle here — that's slow,
requires MLflow artifacts, and belongs in an end-to-end smoke test.
Instead we use the `mock_ml_pipeline` fixture from conftest.py which
patches `get_pipeline()` to return a lightweight MagicMock.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.backend import predict


class TestPredictSample:
    def test_returns_lat_lon_floats(self, mock_ml_pipeline):
        wide_df = pd.DataFrame([{"Bacteroides": 0.4, "Prevotella": 0.3, "Faecalibacterium": 0.3}])
        lat, lon = predict.predict_sample(wide_df)
        assert isinstance(lat, float)
        assert isinstance(lon, float)

    def test_coordinates_are_near_malmo(self, mock_ml_pipeline):
        """
        The mock returns EPSG:3006 coords near Malmö.  After transforming
        to EPSG:4326 we expect roughly (55.6°N, 13.0°E).
        """
        wide_df = pd.DataFrame([{"Bacteroides": 0.4, "Prevotella": 0.3, "Faecalibacterium": 0.3}])
        lat, lon = predict.predict_sample(wide_df)
        assert 55.0 < lat < 56.0
        assert 12.0 < lon < 14.0

    def test_missing_columns_are_filled_with_zero(self, mock_ml_pipeline):
        """
        The pipeline was trained on 3 features, but we only provide 1.
        The wrapper must pad the missing columns with 0.0 rather than
        crashing.
        """
        wide_df = pd.DataFrame([{"Bacteroides": 0.5}])
        predict.predict_sample(wide_df)

        # Inspect what was actually handed to the mock model.
        called_with = mock_ml_pipeline.predict.call_args[0][0]
        assert list(called_with.columns) == ["Bacteroides", "Prevotella", "Faecalibacterium"]
        assert called_with["Prevotella"].iloc[0] == 0.0
        assert called_with["Faecalibacterium"].iloc[0] == 0.0

    def test_extra_columns_are_ignored(self, mock_ml_pipeline):
        """Columns the model doesn't know about must be dropped, not passed in."""
        wide_df = pd.DataFrame([{"Bacteroides": 0.4, "UnknownClade": 0.99, "Faecalibacterium": 0.3}])
        predict.predict_sample(wide_df)
        called_with = mock_ml_pipeline.predict.call_args[0][0]
        assert "UnknownClade" not in called_with.columns


class TestGetPipeline:
    def test_raises_when_model_file_missing(self, monkeypatch, tmp_path):
        # Point MODEL_PATH at a location that definitely doesn't exist.
        monkeypatch.setattr(predict.settings, "MODEL_PATH", tmp_path / "does_not_exist.pkl")
        with pytest.raises(FileNotFoundError):
            predict.get_pipeline()
